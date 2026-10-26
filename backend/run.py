"""Local entry point: python -m backend.run. Container uses the same app factory."""
import os
from .main import create_app
import uvicorn

if __name__=='__main__':
    uvicorn.run(create_app(),host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','4317')),proxy_headers=True,forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS','127.0.0.1'),limit_concurrency=32,timeout_keep_alive=5,access_log=os.getenv('ACCESS_LOG')=='true')
