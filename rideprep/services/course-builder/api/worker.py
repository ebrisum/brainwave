"""RQ worker entry point: `python -m api.worker` (needs REDIS_URL)."""
import os

import redis
from rq import Queue, Worker

if __name__ == "__main__":
    conn = redis.Redis.from_url(os.environ["REDIS_URL"])
    Worker([Queue("builds", connection=conn)], connection=conn).work()
