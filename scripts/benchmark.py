"""Bounded local HTTP benchmark with isolated data; never contacts Git providers."""
import concurrent.futures
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from backend.storage import Store,set_meta
from backend.content import insert
from backend.validation import DEFAULT_PROFILE,validate_record

root=Path(__file__).resolve().parents[1]
directory=Path(tempfile.mkdtemp(prefix='lin-v9-benchmark-'))
store=Store(directory);store.initialize()
with store.transaction() as db:
    set_meta(db,'profile',DEFAULT_PROFILE)
    for n in range(200): insert(db,'posts',validate_record('posts',{'title':f'Article {n}','slug':f'article-{n}','excerpt':'Example','content':'## Reading\n\n'+('Text content. '*300),'category':'Notes','status':'published','publishAt':'2026-01-01T00:00:00Z'}))
port=4358; origin=f'http://127.0.0.1:{port}'
process=subprocess.Popen([sys.executable,'-m','backend.run'],cwd=root,env={**os.environ,'DATA_DIR':str(directory),'PORT':str(port),'APP_ENV':'test','COOKIE_SECURE':'false'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try: urllib.request.urlopen(origin+'/healthz',timeout=1).close();break
        except OSError: time.sleep(.1)
    paths=['/api/public','/api/public/posts/article-1','/','/healthz']
    results={}
    for path in paths:
        def read(_):
            start=time.perf_counter()
            with urllib.request.urlopen(origin+path,timeout=10) as response: size=len(response.read())
            return (time.perf_counter()-start)*1000,size
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: samples=list(pool.map(read,range(80)))
        latency=sorted(v[0] for v in samples)
        results[path]={'requests':80,'concurrency':8,'p50_ms':round(statistics.median(latency),2),'p95_ms':round(latency[75],2),'max_ms':round(max(latency),2),'bytes':samples[0][1]}
    out=root/'test-results/benchmark-v9.json';out.write_text(json.dumps({'articles':200,'environment':'local Windows; not a 2-core server benchmark','results':results},indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
finally:
    process.terminate();process.wait(timeout=10)
