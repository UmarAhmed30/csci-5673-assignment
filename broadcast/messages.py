"""
broadcast/messages.py

Message types for the rotating sequencer atomic broadcast protocol.

All messages are JSON-encoded for transmission over UDP.
Short field keys are used to keep datagrams small.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Optional

MSG_REQUEST    = "REQUEST"
MSG_SEQUENCE   = "SEQUENCE"
MSG_RETRANSMIT = "RETRANSMIT"


@dataclass
class RequestMsg:
    """
    Broadcast by the replica that received the client write.
    Unique ID: (sender_id, local_seq).
    """
    sender_id: int
    local_seq: int
    payload: dict                    # serialised op + args dict
    highest_global_seq_received: int  # piggybacked: confirms everything <= this value


@dataclass
class SequenceMsg:
    """
    Sent by the rotating sequencer to assign global_seq k to a pending Request.
    Sequencer for k is the node whose node_id == k % n.
    """
    global_seq: int
    req_sender_id: int
    req_local_seq: int
    sequencer_id: int
    highest_global_seq_received: int  # piggybacked


@dataclass
class RetransmitMsg:
    """
    Negative acknowledgement — sent to the original sender of a missing message.
    missing_type == "REQUEST"  → ask req sender for (target_sender_id, target_local_seq)
    missing_type == "SEQUENCE" → ask sequencer for missing_global_seq
    missing_type == "ACK"      → proactive state update; no retransmit, just metadata
                                 (ack_up_to: highest gs this node has received fully)
    """
    requester_id: int
    missing_type: Literal["REQUEST", "SEQUENCE", "ACK"]
    # REQUEST fields
    target_sender_id: Optional[int] = None
    target_local_seq: Optional[int] = None
    # SEQUENCE fields
    missing_global_seq: Optional[int] = None
    # ACK fields
    ack_up_to: Optional[int] = None


# ---------------------------------------------------------------------------
# Encode / decode
# ---------------------------------------------------------------------------

def encode(msg) -> bytes:
    if isinstance(msg, RequestMsg):
        d = {
            "t":    MSG_REQUEST,
            "sid":  msg.sender_id,
            "ls":   msg.local_seq,
            "p":    msg.payload,
            "hgsr": msg.highest_global_seq_received,
        }
    elif isinstance(msg, SequenceMsg):
        d = {
            "t":    MSG_SEQUENCE,
            "gs":   msg.global_seq,
            "rsid": msg.req_sender_id,
            "rls":  msg.req_local_seq,
            "sqid": msg.sequencer_id,
            "hgsr": msg.highest_global_seq_received,
        }
    elif isinstance(msg, RetransmitMsg):
        d = {
            "t":   MSG_RETRANSMIT,
            "rid": msg.requester_id,
            "mt":  msg.missing_type,
        }
        if msg.missing_type == "REQUEST":
            d["tsid"] = msg.target_sender_id
            d["tls"]  = msg.target_local_seq
        elif msg.missing_type == "SEQUENCE":
            d["mgs"] = msg.missing_global_seq
        else:  # ACK
            d["atu"] = msg.ack_up_to
    else:
        raise TypeError(f"Cannot encode unknown message type: {type(msg)}")
    return json.dumps(d, separators=(",", ":")).encode()


def decode(data: bytes):
    d = json.loads(data.decode())
    t = d["t"]
    if t == MSG_REQUEST:
        return RequestMsg(
            sender_id=d["sid"],
            local_seq=d["ls"],
            payload=d["p"],
            highest_global_seq_received=d["hgsr"],
        )
    if t == MSG_SEQUENCE:
        return SequenceMsg(
            global_seq=d["gs"],
            req_sender_id=d["rsid"],
            req_local_seq=d["rls"],
            sequencer_id=d["sqid"],
            highest_global_seq_received=d["hgsr"],
        )
    if t == MSG_RETRANSMIT:
        return RetransmitMsg(
            requester_id=d["rid"],
            missing_type=d["mt"],
            target_sender_id=d.get("tsid"),
            target_local_seq=d.get("tls"),
            missing_global_seq=d.get("mgs"),
            ack_up_to=d.get("atu"),
        )
    raise ValueError(f"Unknown message type tag: {t!r}")
