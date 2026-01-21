import json
import struct
import socket
import time

def send_msg(sock: socket.socket, data: dict):
    try:
        payload = json.dumps(data).encode("utf-8")
        msg_len = struct.pack("!I", len(payload))
        sock.sendall(msg_len + payload)
    except Exception as e:
        raise RuntimeError(f"send_msg failed: {e}")


def recv_msg(sock: socket.socket):
    try:
        raw_len = _recv_exact(sock, 4)
        if not raw_len:
            return None
        msg_len = struct.unpack("!I", raw_len)[0]
        payload = _recv_exact(sock, msg_len)
        if not payload:
            return None
        return json.loads(payload.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"recv_msg failed: {e}")


def _recv_exact(sock: socket.socket, n: int):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def success(payload=None):
    return {
        "status": "ok",
        "timestamp": time.time(),
        "data": payload,
    }


def error(message: str):
    return {
        "status": "error",
        "timestamp": time.time(),
        "message": message,
    }
