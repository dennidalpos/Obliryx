# Build on Windows x64 with the pinned packaging environment.
from pathlib import Path
import json
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
ui = root / 'frontend' / 'dist'
if not (ui / 'index.html').is_file():
    raise RuntimeError('Run npm ci and npm run build in frontend first.')
manifest = json.loads((ui / '.vite' / 'manifest.json').read_text(encoding='utf-8'))
assets = {'index.html'}
for chunk in manifest.values():
    assets.add(chunk['file'])
    assets.update(chunk.get('css', []))
    assets.update(chunk.get('assets', []))
ui_data = [(str(ui / asset), 'obliryx/ui/' + str(Path(asset).parent).replace('\\', '/')) for asset in sorted(assets)]
a = Analysis(
    [str(root / 'packaging' / 'desktop-entry.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[*ui_data, *collect_data_files('obliryx'), *collect_data_files('webview')],
    hiddenimports=collect_submodules('webview.platforms', filter=lambda name: name.endswith(('winforms', 'edgechromium'))),
    excludes=['playwright', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'pytest', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Obliryx',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          version=str(root / 'packaging' / 'version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Obliryx')
