"""Question 1 of the Redis checkpointer spike. Stops when setup fails.

Run against a local Redis, default redis://127.0.0.1:6380:

    uv run --with langgraph-checkpoint-redis==0.6.0 python docs/hosted_demo/redis_spike/q1_setup.py
    uv run --with langgraph==1.2.14 --with langgraph-checkpoint-redis==0.6.0 python docs/hosted_demo/redis_spike/q1_setup.py
"""

from __future__ import annotations

import importlib.metadata as metadata
import os
import sys

URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6380")


def main() -> int:
    from langgraph.checkpoint.redis import RedisSaver

    print("langgraph", metadata.version("langgraph"))
    print("langgraph-checkpoint", metadata.version("langgraph-checkpoint"))
    print("langgraph-checkpoint-redis", metadata.version("langgraph-checkpoint-redis"))
    print("url", URL)
    try:
        with RedisSaver.from_conn_string(URL) as saver:
            saver.setup()
    except Exception as exc:
        print(type(exc).__name__)
        print(exc)
        return 1
    print("setup ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
