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
from labprism.artifacts import sha256, verify_media, verify_run, verify_release

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


def publish(nas,data_root,version,evidence=()):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]+',version):raise ValueError('Unsafe version')
    mounts,identity=verify_nas(nas);nas=Path(nas);data_root=Path(data_root)
    project=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','status','--porcelain'],cwd=project,text=True).strip():
        raise ValueError('Commit reviewed source before archiving; working tree is dirty')
    release_root=nas/'releases'
    if release_root.is_symlink():raise ValueError('Release directory cannot be a symlink')
    destination=release_root/version
    destination.mkdir(parents=True,exist_ok=False)
    catalog=json.loads((data_root/'receipts/demo-catalog.json').read_text())
    replay={'schema_version':'labprism-release-replay/1','clips':[],'models':[]}
    used_models={}
    for entry in catalog['clips']:
        if not re.fullmatch(r'[a-z0-9-]+',entry['id']):raise ValueError('Unsafe clip ID')
        run=Path(entry['run']).resolve()
        if not run.is_relative_to((data_root/'runs').resolve()):raise ValueError('Unowned run')
        if any(p.is_symlink() for p in run.rglob('*')):raise ValueError('Run cannot contain symlinks')
        result=verify_run(run)
        for model in result['models']:
            key=(model['id'],model['sha256'])
            if key in used_models and used_models[key]!=model:raise ValueError('Model registry collision')
            used_models[key]=model
        shutil.copytree(run,destination/'runs'/entry['id'])
        producer_hash=sha256(run/'producer-receipt.json')
        media=next((p.parent for p in (data_root/'media').rglob('receipt.json') if sha256(p)==producer_hash),None)
        if media is None:raise ValueError('Complete received media package required for replay')
        if any(p.is_symlink() for p in media.rglob('*')):raise ValueError('Media cannot contain symlinks')
        verify_media(media)
        shutil.copytree(media,destination/'media'/entry['id'])
        recipe={'id':entry['id'],'media':f"media/{entry['id']}",'sample_hz':result['video']['sample_hz'],'mode':'baseline'}
        if result.get('derived_from'):
            parent_hash=result['derived_from']['receipt_sha256']
            parent=next((p.parent for p in (data_root/'runs').rglob('receipt.json') if sha256(p)==parent_hash),None)
            if parent is None or any(p.is_symlink() for p in parent.rglob('*')):raise ValueError('Verified baseline dependency required')
            verify_run(parent)
            shutil.copytree(parent,destination/'parents'/entry['id'])
            recipe.update(mode='candidate',baseline=f"parents/{entry['id']}")
        replay['clips'].append(recipe)
    preview=data_root/'website-preview'
    if any(p.is_symlink() for p in preview.rglob('*')):raise ValueError('Preview must contain owned regular files')
    shutil.copytree(preview,destination/'website')
    shutil.copytree(project/'docs',destination/'documents')
    (destination/'code').mkdir()
    subprocess.run(['git','archive','--format=tar.gz','-o',str(destination/'code/source.tar.gz'),'HEAD'],cwd=project,check=True)
    for m in used_models.values():
        if sha256(m['path'])!=m['sha256']:raise ValueError('Model hash mismatch')
        target=destination/'models'/m['sha256']/Path(m['path']).name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(m['path'],target)
        received=dict(m,path=str(target.relative_to(destination)))
        for name,expected in m.get('auxiliary_files',{}).items():
            original=Path(m['path']).parent/name
            if Path(name).name!=name or sha256(original)!=expected:raise ValueError('Auxiliary model file mismatch')
            shutil.copy2(original,target.parent/name)
        if m.get('producer_receipt'):
            if sha256(m['producer_receipt'])!=m['producer_receipt_sha256']:raise ValueError('Producer model receipt mismatch')
            shutil.copy2(m['producer_receipt'],target.parent/'producer-receipt.json')
            received['producer_receipt']=str((target.parent/'producer-receipt.json').relative_to(destination))
        replay['models'].append(received)
    license_root=data_root/'models/public'
    for name in ['rtmlib-license.txt','mmpose-license.txt']:
        if (license_root/name).is_file():
            (destination/'licenses').mkdir(exist_ok=True)
            shutil.copy2(license_root/name,destination/'licenses'/name)
    (destination/'replay.json').write_text(json.dumps(replay,ensure_ascii=False,indent=2)+'\n')
    for directory in evidence:
        directory=Path(directory).resolve()
        if not directory.is_relative_to((data_root/'evaluations').resolve()) or any(p.is_symlink() for p in directory.rglob('*')):raise ValueError('Unowned evaluation directory')
        shutil.copytree(directory,destination/'evaluations'/directory.name)
    shutil.copytree(data_root/'receipts',destination/'receipts')
    files={str(p.relative_to(destination)):{'sha256':sha256(p),'bytes':p.stat().st_size} for p in destination.rglob('*') if p.is_file()}
    receipt={'schema_version':'labprism-internal-release/1','version':version,'created_at':datetime.now(timezone.utc).isoformat(),'volume':identity,'mounts':mounts,'public_release_authorized':False,'deployment_approved':False,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip(),'files':files}
    (destination/'release.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    for name,item in files.items():
        if sha256(destination/name)!=item['sha256']:raise ValueError('Publication re-read mismatch')
    (destination/'READY.json').write_text(json.dumps({'release_sha256':sha256(destination/'release.json'),'scope':'internal_artifact_integrity_only','algorithm_acceptance':False},indent=2)+'\n')
    verify_release(destination)
    local={'schema_version':'labprism-nas-publication/1','destination':str(destination),'release_sha256':sha256(destination/'release.json'),'files_verified':len(files),'public_release':False}
    (data_root/'receipts'/f'{version}-publication.json').write_text(json.dumps(local,ensure_ascii=False,indent=2)+'\n')
    return local

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('version');p.add_argument('--nas',default=os.getenv('LABPRISM_NAS_ROOT','/mnt/realityloop-nas/LabPrism'));p.add_argument('--data',default=os.getenv('LABPRISM_DATA_ROOT',str(Path.home()/'.local/share/labprism')))
    p.add_argument('--evidence',action='append',default=[],help='Owned evaluation directory to include (repeatable)')
    a=p.parse_args();print(json.dumps(publish(a.nas,a.data,a.version,a.evidence),ensure_ascii=False))
