"""Explicit NAS-backed inspection files, without exposing training artifacts."""
import json
import re
import subprocess
from pathlib import Path
from labprism.artifacts import sha256


def inspection_assets(data_root,nas_root,volume_id):
    manifest=Path(data_root)/'receipts/inspection-preview.json'
    if not manifest.exists():return {},[]
    nas_root=Path(nas_root).resolve()
    marker=json.loads((nas_root/'.labprism-volume.json').read_text())
    mounts=json.loads(subprocess.check_output(['findmnt','-J','-T',str(nas_root),'-o','FSTYPE'],text=True))
    if marker.get('volume_id')!=volume_id or not any(r['fstype'] in {'cifs','nfs','nfs4'} for r in mounts['filesystems']):
        raise ValueError('Inspection NAS identity or mount differs')
    pin=json.loads(manifest.read_text());root=Path(pin['snapshot'])
    if root.is_symlink() or not root.resolve().is_relative_to(nas_root/'media/inspection'):
        raise ValueError('Inspection bundle outside owned NAS media')
    if sha256(root/'receipt.json')!=pin['receipt_sha256']:raise ValueError('Inspection receipt changed')
    receipt=json.loads((root/'receipt.json').read_text())
    if receipt.get('schema_version')!='labprism-inspection-preview/1':raise ValueError('Wrong inspection receipt')
    assets={}
    for name,digest in receipt['files'].items():
        if not re.fullmatch(r'catalog\.json|[a-z0-9-]+/(?:index\.json|result\.json|frames-[0-9]{5}\.json|clip\.mp4)',name):
            raise ValueError('Invalid inspection asset name')
        path=root/name
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or sha256(path)!=digest:
            raise ValueError('Inspection asset hash or path changed')
        stat=path.stat();assets['/inspection/'+name]=(path,stat.st_size,stat.st_mtime_ns)
    if '/inspection/catalog.json' not in assets:raise ValueError('Missing inspection catalog')
    clips=json.loads((root/'catalog.json').read_text())['clips']
    if len({c['id'] for c in clips})!=len(clips):raise ValueError('Duplicate inspection ID')
    for clip in clips:
        for key in ['video','result','download']:
            if '/'+clip[key] not in assets:raise ValueError('Catalog links to unverified inspection file')
    return assets,clips
