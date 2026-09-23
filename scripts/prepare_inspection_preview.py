#!/usr/bin/env python3
"""Publish explicit verified inspection bundles to NAS for loopback preview only."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from labprism.artifacts import sha256,verify_run
from labprism.result_chunks import write_chunks
from labprism.runtime.jobs import write_json
from labprism.inspection_preview import inspection_assets

def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--version',required=True);a=p.parse_args();repo=Path(__file__).resolve().parents[1];cfg=json.loads((repo/'configs/project.json').read_text());nas=Path(os.environ.get('LABPRISM_NAS_ROOT',cfg['nas_root_default']));data=Path(os.environ.get('LABPRISM_DATA_ROOT',cfg['data_root_default']))
 import re
 if not re.fullmatch('[a-z0-9-]+',a.version):raise ValueError('Unsafe version')
 if json.loads((nas/'.labprism-volume.json').read_text())['volume_id']!=cfg['nas_volume_id'] or 'cifs' not in subprocess.check_output(['findmnt','-T',str(nas),'-n','-o','FSTYPE'],text=True):raise ValueError('NAS identity unavailable')
 root=nas/'media/inspection'/a.version;root.mkdir(parents=True,exist_ok=False);manifest=json.loads(a.manifest.read_text());clips=[];producer_pins=[]
 for item in manifest['runs']:
  name=item['id'];run=Path(item['run'])
  if not re.fullmatch('[a-z0-9-]+',name) or run.is_symlink() or not run.resolve().is_relative_to(nas.resolve()):raise ValueError('Unowned inspection input')
  r=verify_run(run);target=root/name;target.mkdir();shutil.copyfile(run/'clip.mp4',target/'clip.mp4');write_chunks(r,target)
  clips.append({'id':name,'title':item['title'],'review_note':item['review_note'],'result':f'inspection/{name}/index.json','download':f'inspection/{name}/result.json','video':f'inspection/{name}/clip.mp4','source_sha256':r['source']['source_sha256'],'clip_sha256':r['source']['clip_sha256'],'camera_id':r['source']['camera_id'],'camera_role':r['source']['camera_role'],'experiment':r['source'].get('experiment',{}).get('experiment_id'),'width':r['video']['width'],'height':r['video']['height']});producer_pins.append({'path':str(run/'receipt.json'),'sha256':sha256(run/'receipt.json')})
 (root/'catalog.json').write_text(json.dumps({'schema_version':'labprism-demo-catalog/1','clips':clips},ensure_ascii=False,indent=2));receipt={'schema_version':'labprism-inspection-preview/1','public_release_authorized':False,'producer_runs':producer_pins,'files':{p.relative_to(root).as_posix():sha256(p) for p in root.rglob('*') if p.is_file()}};(root/'receipt.json').write_text(json.dumps(receipt,indent=2));pin={'snapshot':str(root),'receipt_sha256':sha256(root/'receipt.json')};write_json(data/'receipts/inspection-preview.json',pin);assets,verified=inspection_assets(data,nas,cfg['nas_volume_id']);print(json.dumps({'clips':len(verified),'verified_assets':len(assets),'media_on_nas':True}))
if __name__=='__main__':main()
