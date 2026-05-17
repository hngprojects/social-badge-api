import os
from redis import Redis
from rq import Queue
from dotenv import load_dotenv

load_dotenv()

# Support Redis Cloud via REDIS_URL or local Redis with components
redis_url = os.getenv("REDIS_URL")

if redis_url:
    # Redis Cloud format: redis://default:password@host:port
    redis_conn = Redis.from_url(redis_url, decode_responses=True)
else:
    # Local Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_password = os.getenv("REDIS_PASSWORD")
    
    redis_conn = Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        decode_responses=True
    )

badge_queue = Queue("badge-generation", connection=redis_conn)