"""
broadcast/config.py

Group configuration for the 5-node rotating sequencer broadcast group.
Every env var has a sane localhost default so local testing works out of the box.

Set MY_NODE_ID=0..4 in each replica's .env to identify which node it is.
Set BROADCAST_NODE_<i>_HOST / _PORT for each peer's UDP address.
"""

import os
from dotenv import load_dotenv

load_dotenv()

NODE_GROUP = [
    {
        "id":   0,
        "host": os.getenv("BROADCAST_NODE_0_HOST", "127.0.0.1"),
        "port": int(os.getenv("BROADCAST_NODE_0_PORT", "6100")),
    },
    {
        "id":   1,
        "host": os.getenv("BROADCAST_NODE_1_HOST", "127.0.0.1"),
        "port": int(os.getenv("BROADCAST_NODE_1_PORT", "6101")),
    },
    {
        "id":   2,
        "host": os.getenv("BROADCAST_NODE_2_HOST", "127.0.0.1"),
        "port": int(os.getenv("BROADCAST_NODE_2_PORT", "6102")),
    },
    {
        "id":   3,
        "host": os.getenv("BROADCAST_NODE_3_HOST", "127.0.0.1"),
        "port": int(os.getenv("BROADCAST_NODE_3_PORT", "6103")),
    },
    {
        "id":   4,
        "host": os.getenv("BROADCAST_NODE_4_HOST", "127.0.0.1"),
        "port": int(os.getenv("BROADCAST_NODE_4_PORT", "6104")),
    },
]

MY_NODE_ID      = int(os.getenv("MY_NODE_ID", "0"))
N               = len(NODE_GROUP)
MAJORITY        = (N // 2) + 1   # 3 of 5
UDP_BUFFER_SIZE = 65535
