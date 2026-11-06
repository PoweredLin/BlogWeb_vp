"""Fetch pinned open fonts and their licenses; runtime pages use local files only."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'inter-latin.woff2': 'https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.2.8/files/inter-latin-wght-normal.woff2',
    'lora-latin.woff2': 'https://cdn.jsdelivr.net/npm/@fontsource-variable/lora@5.2.8/files/lora-latin-wght-normal.woff2',
    'Inter-OFL.txt': 'https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.2.8/LICENSE',
    'Lora-OFL.txt': 'https://cdn.jsdelivr.net/npm/@fontsource-variable/lora@5.2.8/LICENSE',
}

if __name__ == '__main__':
    target = ROOT / 'public/fonts'
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, url in FILES.items():
        try:
            body = urllib.request.urlopen(url, timeout=30).read()
        except OSError:
            url = url.replace('https://cdn.jsdelivr.net/npm/', 'https://unpkg.com/')
            body = urllib.request.urlopen(url, timeout=30).read()
        if name.endswith('.woff2') and body[:4] != b'wOF2':
            raise ValueError('Expected WOFF2: ' + name)
        (target / name).write_bytes(body)
        manifest.append({'file': name, 'source': url, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()})
        print(name, len(body))
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
