#!/usr/bin/env python3
"""Publish an immutable internal NAS artifact; never exposes a public website."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from labprism.artifacts import sha256
from labprism.contracts import validate_result

EXPECTED_VOLUME = 'b01a5b29-90f0-4bf4-b060-416f4fc67da0'


def verify_nas(nas):
    nas=Path(nas)
    if nas.is_symlink() or nas.resolve()!=nas.absolute():raise ValueError('NAS must not redirect through symlinks')
    mounts=json.loads(subprocess.check_output(['findmnt','-J','-T',str(nas)],text=True))['filesystems']
    real=[m for m in mounts if m['fstype'] in {'cifs','nfs','nfs4'}]
    if not real:raise ValueError('Actual network filesystem mount required')
    identity=json.loads((nas/'.labprism-volume.json').read_text())
    if identity.get('project')!='LabPrism' or identity.get('volume_id')!=EXPECTED_VOLUME:
        raise ValueError('NAS volume identity mismatch')
    return real,identity


def publish(nas,data_root,version):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]+',version):raise ValueError('Unsafe version')
    mounts,identity=verify_nas(nas);nas=Path(nas);data_root=Path(data_root)
    release_root=nas/'releases'
    if release_root.is_symlink():raise ValueError('Release directory cannot be a symlink')
    destination=release_root/version
    destination.mkdir(parents=True,exist_ok=False)
    catalog=json.loads((data_root/'receipts/demo-catalog.json').read_text())
    for entry in catalog['clips']:
        run=Path(entry['run']).resolve()
        if not run.is_relative_to((data_root/'runs').resolve()):raise ValueError('Unowned run')
        receipt=json.loads((run/'receipt.json').read_text())
        validate_result(json.loads((run/'result.json').read_text()))
        for name,h in receipt['files'].items():
            if Path(name).name!=name or sha256(run/name)!=h:raise ValueError('Run hash mismatch')
        shutil.copytree(run,destination/'runs'/entry['id'])
    preview=data_root/'website-preview'
    if any(p.is_symlink() for p in preview.rglob('*')):raise ValueError('Preview must contain owned regular files')
    shutil.copytree(preview,destination/'website')
    project=Path(__file__).resolve().parents[1]
    shutil.copytree(project/'docs',destination/'documents')
    (destination/'code').mkdir()
    subprocess.run(['git','archive','--format=tar.gz','-o',str(destination/'code/source.tar.gz'),'HEAD'],cwd=project,check=True)
    models=json.loads((data_root/'receipts/baseline-models-20260917.json').read_text())
    for m in models['models']:
        if sha256(m['path'])!=m['sha256']:raise ValueError('Model hash mismatch')
        target=destination/'models'/m['sha256']/Path(m['path']).name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(m['path'],target)
        if m.get('producer_receipt'):shutil.copy2(m['producer_receipt'],target.parent/'producer-receipt.json')
    shutil.copytree(data_root/'receipts',destination/'receipts')
    files={str(p.relative_to(destination)):{'sha256':sha256(p),'bytes':p.stat().st_size} for p in destination.rglob('*') if p.is_file()}
    receipt={'schema_version':'labprism-internal-release/1','version':version,'created_at':datetime.now(timezone.utc).isoformat(),'volume':identity,'mounts':mounts,'public_release_authorized':False,'deployment_approved':False,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip(),'files':files}
    (destination/'release.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    for name,item in files.items():
        if sha256(destination/name)!=item['sha256']:raise ValueError('Publication re-read mismatch')
    (destination/'READY.json').write_text(json.dumps({'release_sha256':sha256(destination/'release.json'),'scope':'internal_artifact_integrity_only','algorithm_acceptance':False},indent=2)+'\n')
    local={'schema_version':'labprism-nas-publication/1','destination':str(destination),'release_sha256':sha256(destination/'release.json'),'files_verified':len(files),'public_release':False}
    (data_root/'receipts'/f'{version}-publication.json').write_text(json.dumps(local,ensure_ascii=False,indent=2)+'\n')
    return local

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('version');p.add_argument('--nas',default=os.getenv('LABPRISM_NAS_ROOT','/mnt/realityloop-nas/LabPrism'));p.add_argument('--data',default=os.getenv('LABPRISM_DATA_ROOT',str(Path.home()/'.local/share/labprism')))
    a=p.parse_args();print(json.dumps(publish(a.nas,a.data,a.version),ensure_ascii=False))
