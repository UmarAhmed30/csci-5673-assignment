"""
broadcast/node.py

BroadcastNode — rotating sequencer atomic broadcast over UDP.

Threading model
---------------
  _recv_loop      : one background thread; reads UDP datagrams and dispatches
  _sequencer_loop : one background thread; uses a Condition to wait for eligible
                    requests, then sends SEQUENCE messages when it is the sequencer
  _delivery_loop  : one background thread; applies delivered ops to the DB in order
                    (no lock held during the DB call)
  gRPC threads    : call broadcast_request() which blocks on a Future until the
                    operation is fully delivered and apply_fn returns

All shared state is protected by self._lock (threading.Lock).
self._seq_condition is a threading.Condition that wraps self._lock.
"""

from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Callable, Optional

from broadcast.messages import (
    RetransmitMsg,
    RequestMsg,
    SequenceMsg,
    decode,
    encode,
)
from broadcast.config import MAJORITY, MY_NODE_ID, N, NODE_GROUP, UDP_BUFFER_SIZE

logger = logging.getLogger(__name__)


class BroadcastNode:
    """
    One instance per replica process.

    Parameters
    ----------
    apply_fn : callable
        Called by _delivery_loop for each delivered operation in global order.
        Signature: apply_fn(payload: dict) -> result
        - payload contains {"op": str, "args": dict}
        - result is returned to the waiting gRPC thread via a Future
        - raise an exception to signal failure (it is forwarded to the caller)
    """

    def __init__(self, apply_fn: Callable[[dict], object]):
        self.node_id  = MY_NODE_ID
        self.apply_fn = apply_fn
        self._peers   = {n["id"]: (n["host"], n["port"]) for n in NODE_GROUP}
        self._my_addr = self._peers[self.node_id]

        # ------------------------------------------------------------------ #
        # Shared state — all access must hold self._lock                      #
        # ------------------------------------------------------------------ #
        self._lock          = threading.Lock()
        self._seq_condition = threading.Condition(self._lock)

        # Monotonically increasing counter for requests this node originates.
        self._local_seq_counter: int = 0

        # Highest local_seq received from each sender, for gap detection.
        # Index is sender node_id; value -1 means nothing received yet.
        self._hlsr: dict[int, int] = {i: -1 for i in range(N)}

        # All received Request and Sequence messages.
        self._request_store:  dict[tuple, RequestMsg] = {}   # (sender_id, ls) -> msg
        self._sequence_store: dict[int,   SequenceMsg] = {}  # global_seq -> msg

        # Highest global_seq that each peer has confirmed receiving.
        # Derived from the highest_global_seq_received scalar piggybacked on every
        # incoming message.  A value of k means that peer has received all Requests
        # and Sequences with global_seq <= k.
        # Self-entry is initialised to -1 here and updated after each local delivery.
        self._node_confirmed: dict[int, int] = {i: -1 for i in range(N)}

        # Deduplication sets.
        self._seen_req: set[tuple] = set()  # (sender_id, local_seq)
        self._seen_seq: set[int]   = set()  # global_seq

        # Strict in-order delivery pointer.
        self._next_to_deliver: int = 0

        # Next global_seq this node is waiting to assign (sequencer role).
        self._next_global_seq: int = 0

        # Futures waiting for delivery results, keyed by (sender_id, local_seq).
        # Only this node's own writes have entries here.
        self._pending_futures: dict[tuple, Future] = {}

        # Cache of raw UDP bytes for retransmit.
        # Only stores packets that THIS node originated:
        #   ("req", node_id, local_seq)  — my own Request messages
        #   ("seq", global_seq)          — Sequence messages I sent as sequencer
        self._sent_cache: dict[tuple, bytes] = {}

        # Requests received but not yet assigned a global sequence number.
        self._unsequenced: list[RequestMsg] = []

        # ------------------------------------------------------------------ #
        # End shared state                                                     #
        # ------------------------------------------------------------------ #

        # Delivery queue: items are (global_seq, req_key, payload, future|None).
        # Written inside _lock (in _try_deliver), read outside _lock (in _delivery_loop).
        self._delivery_queue: queue.Queue = queue.Queue()

        # UDP socket.
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(self._my_addr)
        self._running = False

    # ---------------------------------------------------------------------- #
    # Lifecycle                                                                #
    # ---------------------------------------------------------------------- #

    def start(self):
        self._running = True
        threading.Thread(
            target=self._recv_loop,
            daemon=True,
            name=f"bc-recv-{self.node_id}",
        ).start()
        threading.Thread(
            target=self._sequencer_loop,
            daemon=True,
            name=f"bc-seq-{self.node_id}",
        ).start()
        threading.Thread(
            target=self._delivery_loop,
            daemon=True,
            name=f"bc-dlv-{self.node_id}",
        ).start()
        logger.info("[Node %d] started on %s", self.node_id, self._my_addr)

    def stop(self):
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    # ---------------------------------------------------------------------- #
    # Public API                                                               #
    # ---------------------------------------------------------------------- #

    def broadcast_request(self, payload: dict) -> object:
        """
        Broadcast a write operation to all replicas and block until this node
        delivers it and apply_fn returns.

        Called from the gRPC servicer thread for every write RPC.
        """
        future: Future = Future()

        with self._lock:
            ls  = self._local_seq_counter
            self._local_seq_counter += 1
            key = (self.node_id, ls)
            self._pending_futures[key] = future
            hgsr = max(self._node_confirmed.values())

        msg = RequestMsg(
            sender_id=self.node_id,
            local_seq=ls,
            payload=payload,
            highest_global_seq_received=hgsr,
        )
        raw = encode(msg)

        with self._lock:
            self._sent_cache[("req", self.node_id, ls)] = raw

        self._send_to_all(raw)
        # On Windows, UDP sockets bound to 0.0.0.0 often do not receive their
        # own loopback packets.  Process the REQUEST locally as well so that
        # this node's _request_store and _unsequenced are populated regardless.
        # _seen_req deduplication makes this idempotent if self-send did work.
        self._on_request(msg)
        return future.result()   # blocks until _delivery_loop resolves it

    def get_next_to_deliver(self) -> int:
        """Return the current strict delivery pointer (used by read-blocking)."""
        with self._lock:
            return self._next_to_deliver

    def has_pending_deliveries(self) -> bool:
        """
        True when there are Sequence messages in the store that have not yet
        been delivered.  Used to block reads until the replica is current.
        """
        with self._lock:
            max_known = max(self._sequence_store.keys(), default=-1)
            return max_known >= self._next_to_deliver

    # ---------------------------------------------------------------------- #
    # UDP send helpers                                                         #
    # ---------------------------------------------------------------------- #

    def _send_to_all(self, raw: bytes):
        for nid, addr in self._peers.items():
            self._udp_send(raw, addr, nid)

    def _send_to(self, raw: bytes, nid: int):
        self._udp_send(raw, self._peers[nid], nid)

    def _udp_send(self, raw: bytes, addr: tuple, nid: int):
        try:
            self._sock.sendto(raw, addr)
        except Exception as exc:
            logger.warning("[Node %d] send→node %d failed: %s", self.node_id, nid, exc)

    # ---------------------------------------------------------------------- #
    # Receive loop                                                             #
    # ---------------------------------------------------------------------- #

    def _recv_loop(self):
        while self._running:
            try:
                data, _ = self._sock.recvfrom(UDP_BUFFER_SIZE)
            except OSError:
                break
            except Exception as exc:
                logger.error("[Node %d] recvfrom error: %s", self.node_id, exc)
                continue
            try:
                msg = decode(data)
            except Exception as exc:
                logger.warning("[Node %d] decode error: %s", self.node_id, exc)
                continue
            try:
                if isinstance(msg, RequestMsg):
                    self._on_request(msg)
                elif isinstance(msg, SequenceMsg):
                    self._on_sequence(msg)
                elif isinstance(msg, RetransmitMsg):
                    self._on_retransmit(msg)
            except Exception as exc:
                logger.error("[Node %d] handler error: %s", self.node_id, exc, exc_info=True)

    # ---------------------------------------------------------------------- #
    # Message handlers                                                         #
    # ---------------------------------------------------------------------- #

    def _on_request(self, msg: RequestMsg):
        retransmits: list[tuple[bytes, int]] = []

        with self._lock:
            key = (msg.sender_id, msg.local_seq)
            if key in self._seen_req:
                return
            self._seen_req.add(key)
            self._request_store[key] = msg

            # Update confirmed state from piggybacked scalar.
            # node X reporting hgsr=k means X has received everything up to k.
            self._node_confirmed[msg.sender_id] = max(
                self._node_confirmed[msg.sender_id],
                msg.highest_global_seq_received,
            )

            # Per-sender local_seq gap detection.
            expected = self._hlsr[msg.sender_id] + 1
            if msg.local_seq > expected:
                for missing_ls in range(expected, msg.local_seq):
                    retransmits.append((
                        encode(RetransmitMsg(
                            requester_id=self.node_id,
                            missing_type="REQUEST",
                            target_sender_id=msg.sender_id,
                            target_local_seq=missing_ls,
                        )),
                        msg.sender_id,
                    ))
            self._hlsr[msg.sender_id] = max(self._hlsr[msg.sender_id], msg.local_seq)

            self._unsequenced.append(msg)
            self._seq_condition.notify_all()
            # NOTE: _try_deliver is NOT called here.
            # Delivery requires a Sequence message (condition 2); calling it now
            # would always be a no-op and wastes cycles.

            # Update self-entry in case the arrival of this Request completes a
            # pair (Sequence already present, Request was the missing half).
            prev = self._node_confirmed[self.node_id]
            new_confirmed = self._update_self_confirmed()

        ack_raw = None
        if new_confirmed > prev:
            ack_raw = encode(RetransmitMsg(
                requester_id=self.node_id,
                missing_type="ACK",
                ack_up_to=new_confirmed,
            ))

        for raw_rt, target_nid in retransmits:
            self._send_to(raw_rt, target_nid)
        if ack_raw is not None:
            self._send_to_all(ack_raw)

    def _on_sequence(self, msg: SequenceMsg):
        retransmits: list[tuple[bytes, int]] = []
        ack_raw = None

        with self._lock:
            if msg.global_seq in self._seen_seq:
                return
            self._seen_seq.add(msg.global_seq)
            self._sequence_store[msg.global_seq] = msg

            # Update confirmed state from piggybacked scalar.
            self._node_confirmed[msg.sequencer_id] = max(
                self._node_confirmed[msg.sequencer_id],
                msg.highest_global_seq_received,
            )

            # Global_seq gap detection: check every seq between next_to_deliver
            # and the just-arrived global_seq for missing Sequence messages.
            for missing_gs in range(self._next_to_deliver, msg.global_seq):
                if missing_gs not in self._sequence_store:
                    expected_sequencer = missing_gs % N
                    retransmits.append((
                        encode(RetransmitMsg(
                            requester_id=self.node_id,
                            missing_type="SEQUENCE",
                            missing_global_seq=missing_gs,
                        )),
                        expected_sequencer,
                    ))

            # All nodes track the global next-to-assign pointer, not just the
            # sequencer.  Without this, non-sequencer nodes would keep checking
            # k=0 in _sequencer_loop and never become eligible for gs=1, gs=2, etc.
            if msg.global_seq + 1 > self._next_global_seq:
                self._next_global_seq = msg.global_seq + 1
                self._seq_condition.notify_all()

            # Remove the now-sequenced request from _unsequenced on ALL nodes.
            # Only the sequencer node removes it via _unsequenced.remove() in
            # _sequencer_loop.  Without this cleanup, every other node still
            # holds the request in _unsequenced and will re-sequence it when
            # their turn as sequencer comes — causing each logical operation to
            # consume N global_seqs instead of one.
            req_key = (msg.req_sender_id, msg.req_local_seq)
            self._unsequenced = [
                r for r in self._unsequenced
                if (r.sender_id, r.local_seq) != req_key
            ]

            # Receiving a Sequence may complete a Request+Sequence pair locally.
            # Update the self-entry to reflect what this node has now received.
            prev = self._node_confirmed[self.node_id]
            new_confirmed = self._update_self_confirmed()
            if new_confirmed > prev:
                ack_raw = encode(RetransmitMsg(
                    requester_id=self.node_id,
                    missing_type="ACK",
                    ack_up_to=new_confirmed,
                ))

            self._try_deliver()

        for raw_rt, target_nid in retransmits:
            self._send_to(raw_rt, target_nid)
        if ack_raw is not None:
            self._send_to_all(ack_raw)

    def _on_retransmit(self, msg: RetransmitMsg):
        """Respond to a NACK by re-sending the requested packet from sent_cache,
        or update node_confirmed from a peer's ACK state-update."""
        raw = None

        with self._lock:
            if msg.missing_type == "ACK":
                # Proactive state update from peer — update their confirmed entry
                # and re-check delivery conditions.
                self._node_confirmed[msg.requester_id] = max(
                    self._node_confirmed[msg.requester_id],
                    msg.ack_up_to,
                )
                self._try_deliver()
                return

            if msg.missing_type == "REQUEST":
                if msg.target_sender_id != self.node_id:
                    return   # only the original sender can retransmit its own request
                key = ("req", self.node_id, msg.target_local_seq)
            else:
                if msg.missing_global_seq % N != self.node_id:
                    return   # only the original sequencer retransmits its own sequence
                key = ("seq", msg.missing_global_seq)
            raw = self._sent_cache.get(key)

        if raw:
            self._send_to(raw, msg.requester_id)

    # ---------------------------------------------------------------------- #
    # Self-confirmation helper — MUST be called with self._lock held          #
    # ---------------------------------------------------------------------- #

    def _update_self_confirmed(self) -> int:
        """
        Recompute node_confirmed[self] based on what is present in local stores
        (received), not just what has been delivered.

        Scans from _next_to_deliver upward, advancing as long as both the
        Sequence message and its corresponding Request message exist in the
        stores.  Returns the new (possibly unchanged) self-entry value.

        Must be called with self._lock held.
        """
        g = self._next_to_deliver
        while True:
            seq_msg = self._sequence_store.get(g)
            if seq_msg is None:
                break
            req_key = (seq_msg.req_sender_id, seq_msg.req_local_seq)
            if req_key not in self._request_store:
                break
            g += 1
        # g-1 is the highest gs for which both Request and Sequence are present.
        new_val = g - 1
        self._node_confirmed[self.node_id] = max(
            self._node_confirmed[self.node_id], new_val
        )
        return self._node_confirmed[self.node_id]

    # ---------------------------------------------------------------------- #
    # Delivery helper — MUST be called with self._lock held                   #
    # ---------------------------------------------------------------------- #

    def _try_deliver(self):
        """
        Drain all deliverable entries from sequence_store into _delivery_queue.

        Implements a strict while-loop (not recursive, not re-notify) so that a
        burst of already-received sequences is drained in a single call rather
        than one delivery per incoming message.

        Advances _next_to_deliver and self._node_confirmed[self.node_id] inside
        the lock BEFORE putting work on the delivery queue, preventing any other
        thread from delivering the same entry.
        """
        while True:
            s = self._next_to_deliver

            # Condition 1: Sequence message for s is available.
            seq_msg = self._sequence_store.get(s)
            if seq_msg is None:
                break

            # Condition 2: Corresponding Request is available.
            req_key = (seq_msg.req_sender_id, seq_msg.req_local_seq)
            if req_key not in self._request_store:
                break

            # Condition 3 (spec-accurate): a majority of nodes have confirmed
            # receiving everything up to and including s.
            # Each node's confirmation is the scalar piggybacked on its messages,
            # which subsumes all entries <= that value.
            confirmed = sum(
                1 for v in self._node_confirmed.values() if v >= s
            )
            if confirmed < MAJORITY:
                break

            # ---- All conditions satisfied --------------------------------- #

            # Advance pointer first — prevents any concurrent path from delivering s.
            self._next_to_deliver += 1
            self._node_confirmed[self.node_id] = self._next_to_deliver - 1
            self._seq_condition.notify_all()  # unblocks sequencer pre-condition checks

            payload = self._request_store[req_key].payload
            future  = self._pending_futures.pop(req_key, None)

            # Evict sent_cache now that majority has confirmed this entry.
            self._sent_cache.pop(("seq", s), None)
            self._sent_cache.pop(("req", req_key[0], req_key[1]), None)

            self._delivery_queue.put((s, req_key, payload, future))
            # Loop immediately — check s+1 without waiting for the next packet.

    # ---------------------------------------------------------------------- #
    # Delivery loop — dedicated thread, no lock held during apply_fn call     #
    # ---------------------------------------------------------------------- #

    def _delivery_loop(self):
        while self._running:
            try:
                item = self._delivery_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            s, req_key, payload, future = item
            try:
                result = self.apply_fn(payload)
                self._write_op_log(s, req_key, payload)
            except Exception as exc:
                logger.error(
                    "[Node %d] apply_fn failed gs=%d: %s",
                    self.node_id, s, exc, exc_info=True,
                )
                result = exc

            if future is not None:
                if isinstance(result, Exception):
                    future.set_exception(result)
                else:
                    future.set_result(result)

    # ---------------------------------------------------------------------- #
    # Sequencer loop — dedicated thread                                        #
    # ---------------------------------------------------------------------- #

    def _sequencer_loop(self):
        """
        Waits until:
          1. This node is the sequencer for _next_global_seq  (k % N == node_id)
          2. All three sequencer pre-conditions are met
          3. At least one eligible request exists in _unsequenced

        Then assigns global_seq k to the chosen request and broadcasts a SEQUENCE.
        Uses threading.Condition (not a spin/sleep loop) to avoid wasted CPU.
        """
        while self._running:
            raw_to_send: Optional[bytes] = None

            with self._lock:
                while self._running:
                    k = self._next_global_seq
                    if (
                        k % N == self.node_id
                        and self._sequencer_preconditions_met(k)
                        and self._pick_eligible(k) is not None
                    ):
                        break
                    self._seq_condition.wait(timeout=0.05)

                if not self._running:
                    break

                k         = self._next_global_seq
                candidate = self._pick_eligible(k)
                assert candidate is not None, "pick_eligible returned None after condition check"

                hgsr = max(self._node_confirmed.values())
                seq_msg = SequenceMsg(
                    global_seq=k,
                    req_sender_id=candidate.sender_id,
                    req_local_seq=candidate.local_seq,
                    sequencer_id=self.node_id,
                    highest_global_seq_received=hgsr,
                )
                raw_to_send = encode(seq_msg)
                self._sent_cache[("seq", k)] = raw_to_send
                self._next_global_seq += 1
                self._unsequenced.remove(candidate)

            # Send outside the lock so we don't block message handlers.
            if raw_to_send is not None:
                self._send_to_all(raw_to_send)
                # Process our own SEQUENCE locally for the same reason as
                # broadcast_request/_on_request: Windows UDP loopback may not
                # deliver self-sent packets.  _seen_seq makes this idempotent.
                self._on_sequence(seq_msg)

    def _sequencer_preconditions_met(self, k: int) -> bool:
        """
        Pre-condition 1: all Sequence messages with global_seq < k are received.
        Pre-condition 2: all Request messages assigned global_seq < k are received.
        Pre-condition 3 is enforced per-candidate in _pick_eligible.
        Called with self._lock held.
        """
        for g in range(k):
            seq = self._sequence_store.get(g)
            if seq is None:
                return False   # pre-condition 1
            if (seq.req_sender_id, seq.req_local_seq) not in self._request_store:
                return False   # pre-condition 2
        return True

    def _pick_eligible(self, k: int) -> Optional[RequestMsg]:
        """
        Find a request in _unsequenced whose entire causal prefix is already
        globally sequenced.

        Pre-condition 3: all Requests from the same sender with a lower local_seq
        must already appear in sequence_store for some global_seq < k.
        The _unsequenced list is scanned (not a blind FIFO pop) to find the first
        eligible candidate, regardless of arrival order.

        Called with self._lock held.
        """
        sequenced_keys: set[tuple] = set()
        for g in range(k):
            seq = self._sequence_store.get(g)
            if seq:
                sequenced_keys.add((seq.req_sender_id, seq.req_local_seq))

        for req in self._unsequenced:
            prefix_clear = all(
                (req.sender_id, ls) in sequenced_keys
                for ls in range(req.local_seq)
            )
            if prefix_clear:
                return req
        return None

    # ---------------------------------------------------------------------- #
    # Operation log (optional, for debugging)                                 #
    # ---------------------------------------------------------------------- #

    def _write_op_log(self, global_seq: int, req_key: tuple, payload: dict):
        try:
            entry = {
                "gs":  global_seq,
                "sid": req_key[0],
                "ls":  req_key[1],
                "op":  payload.get("op"),
                "ts":  time.time(),
            }
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            log_path = log_dir / f"operation_log_node{self.node_id}.jsonl"
            with open(log_path, "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("[Node %d] op log write failed: %s", self.node_id, exc)
