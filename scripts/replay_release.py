#!/usr/bin/env python3
"""Verify an internal release and rerun a clip using its shipped media and weights."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from labprism.artifacts import sha256, verify_release


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('release',type=Path)
    p.add_argument('output',type=Path,nargs='?')
    p.add_argument('--clip')
    p.add_argument('--verify-only',action='store_true')
    args=p.parse_args()
    release=args.release.resolve()
    manifest=verify_release(release)
    print(json.dumps({'version':manifest['version'],'files_verified':len(manifest['files'])}),flush=True)
    if args.verify_only:return
    if args.output is None or args.clip is None:p.error('output and --clip are required for inference')
    if args.output.resolve().is_relative_to(release):p.error('Replay output must be outside the immutable release')
    replay=json.loads((release/'replay.json').read_text())
    entry=next(c for c in replay['clips'] if c['id']==args.clip)
    def member(name):
        path=release/name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(release):raise ValueError('Unowned replay input')
        return path
    models=[]
    for m in replay['models']:
        model=dict(m,path=str(member(m['path'])))
        if m.get('producer_receipt'):model['producer_receipt']=str(member(m['producer_receipt']))
        models.append(model)
    args.output.mkdir(parents=True,exist_ok=False)
    registry=args.output/'relocated-model-receipt.json'
    registry.write_text(json.dumps({'schema_version':'labprism-model-receipt/1','source_release':{'manifest':str(release/'release.json'),'sha256':sha256(release/'release.json'),'git_commit':manifest['git_commit'],'source_archive_sha256':manifest['files']['code/source.tar.gz']['sha256']},'models':models},ensure_ascii=False,indent=2)+'\n')
    if entry.get('mode','baseline')=='candidate':
        from labprism.perception.candidate import run
        run(member(entry['baseline']),args.output/args.clip,registry)
    else:
        from labprism.perception.baseline import run
        run(member(entry['media']),args.output/args.clip,registry,entry['sample_hz'])


if __name__=='__main__':main()
