"""Lock the installed runtime dependency closure, excluding test/audit tools."""
from importlib.metadata import distribution
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
root=Path(__file__).resolve().parents[1]
queue=[Requirement(line).name for line in (root/'backend/requirements.txt').read_text().splitlines() if line and not line.startswith('#')]
locked={}
while queue:
    name=canonicalize_name(queue.pop())
    if name in locked: continue
    package=distribution(name); locked[name]=package.version
    for raw in package.requires or []:
        req=Requirement(raw)
        if not req.marker or req.marker.evaluate({'extra':''}): queue.append(req.name)
(root/'backend/requirements.lock.txt').write_text('# Generated from tested runtime dependencies. Update with scripts/lock-python.py.\n'+'\n'.join(f'{name}=={version}' for name,version in sorted(locked.items()))+'\n',encoding='utf-8')
