"""Push local AI text to a private approval inbox, using only Python stdlib."""
import argparse
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def main():
    p=argparse.ArgumentParser(description='Submit a local AI report to the website approval inbox')
    p.add_argument('--site',default=os.getenv('SPACE_SITE_URL','http://127.0.0.1:4321'))
    p.add_argument('--flow',required=True);p.add_argument('--title',required=True)
    p.add_argument('--file',required=True);p.add_argument('--key',required=True)
    a=p.parse_args();token=os.getenv('SPACE_ACCESS_TOKEN','');site=a.site.rstrip('/');url=urlsplit(site)
    if not token.startswith('sk-'):p.error('Set SPACE_ACCESS_TOKEN in your local environment; never commit it')
    if url.path or url.query or url.fragment or url.username or (url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','localhost'))):p.error('Use an HTTPS origin (HTTP allowed only for localhost)')
    from pathlib import Path
    source=Path(a.file)
    if source.stat().st_size>400000:p.error('Report file is too large')
    content=source.read_text(encoding='utf-8')
    if len(content)>100000:p.error('Report exceeds 100000 characters')
    body=json.dumps({'flowId':a.flow,'title':a.title,'content':content},ensure_ascii=False).encode()
    req=Request(site+'/api/v1/automation/results',data=body,method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+token,'Idempotency-Key':a.key})
    try:
        with urlopen(req,timeout=20) as response:r=json.load(response)
        print(json.dumps({k:r[k] for k in ('id','state','created')},ensure_ascii=False))
    except HTTPError as e:
        try:message=json.load(e).get('error','Request failed')
        except Exception:message='Request failed'
        print(f'HTTP {e.code}: {message}',file=sys.stderr);raise SystemExit(1)

if __name__=='__main__':main()
