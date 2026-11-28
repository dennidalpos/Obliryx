"""Inventory only public distribution inputs; never inspect operational archives."""
import hashlib
import argparse
import importlib.metadata
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--directory', type=Path, default=root / 'dist')
destination = parser.parse_args().directory.resolve()
if not destination.is_relative_to((root / 'dist').resolve()):
    raise SystemExit('Inventory destination must be within dist/.')
packages = []
javascript_packages = []
licenses = destination / 'licenses'
licenses.mkdir(exist_ok=True)
for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = dist.metadata['Name']
    packages.append({'name': name, 'version': dist.version, 'license': dist.metadata.get('License-Expression') or dist.metadata.get('License', '')})
    for file in dist.files or []:
        if '.dist-info/' in str(file).replace('\\', '/') and any(word in file.name.lower() for word in ['license', 'copying', 'notice']):
            target = licenses / (name + '-' + hashlib.sha256(str(file).encode()).hexdigest()[:8] + '-' + file.name)
            if not target.exists():
                target.write_bytes(dist.locate_file(file).read_bytes())
lock = json.loads((root / 'frontend' / 'package-lock.json').read_text(encoding='utf-8'))
for relative, package in lock['packages'].items():
    if not relative:
        continue
    name = relative.rsplit('node_modules/', 1)[-1]
    javascript_packages.append({'name':name, 'version':package['version'],
                                'license':package.get('license', ''), 'development':package.get('dev', False)})
    directory = root / 'frontend' / relative
    for file in directory.glob('*') if directory.is_dir() else []:
        if file.is_file() and any(word in file.name.lower() for word in ['license', 'copying', 'notice']):
            target = licenses / ('npm-' + name.replace('/', '-') + '-' + file.name)
            if not target.exists():
                target.write_bytes(file.read_bytes())
inventory = []
for file in sorted(destination.rglob('*')):
    if not file.is_file() or file.name in {'inventory.json', 'SHA256SUMS.txt'}:
        continue
    if file.suffix.lower() in {'.eml', '.mbox', '.sqlite3', '.env'} or '.sqlite3' in file.name:
        raise SystemExit('Sensitive file extension found in release; inspect artifacts locally.')
    inventory.append({'path': file.relative_to(destination).as_posix(),
                      'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'bytes': file.stat().st_size})
(destination / 'inventory.json').write_text(json.dumps({'schema': 1, 'packages': packages, 'javascript_packages':javascript_packages, 'files': inventory}, indent=2), encoding='utf-8')
(destination / 'SHA256SUMS.txt').write_text(''.join(f"{item['sha256']}  {item['path']}\n" for item in inventory), encoding='utf-8')
print(f'Inventoried {len(inventory)} files and {len(packages)} Python distributions.')
