#!/usr/bin/env python3
"""Serve only verified preview artifacts on loopback, with video range requests."""
import argparse
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from labprism.artifacts import sha256, verify_run


def copy_file(source, destination):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('Preview files cannot be symlinks')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def prepare(project, data_root):
    destination = data_root / 'website-preview'
    if destination.is_symlink(): raise ValueError('Preview directory cannot be a symlink')
    destination.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((data_root / 'receipts/website-media-import.json').read_text())
    asset = data_root / 'media/website/lab-scene.png'
    if sha256(asset) != receipt['sha256']: raise ValueError('Preview image hash mismatch')
    for folder, relative in [(project/'apps/website',Path('.')), (project/'apps/viewer',Path('viewer'))]:
        if (destination/relative).is_symlink():raise ValueError('Unsafe preview directory')
        for p in folder.iterdir():
            if p.is_file() and p.suffix in {'.html','.js','.css'}:copy_file(p,destination/relative/p.name)
    if (destination/'assets').is_symlink(): raise ValueError('Unsafe assets directory')
    copy_file(asset,destination/'assets/lab-scene.png')
    catalog_path=data_root/'receipts/demo-catalog.json'
    if catalog_path.exists():
        catalog=json.loads(catalog_path.read_text()); public={'schema_version':'labprism-demo-catalog/1','clips':[]}
        for item in catalog['clips']:
            name=item['id']
            if not re.fullmatch(r'[a-z0-9-]+',name): raise ValueError('Unsafe demo ID')
            run=Path(item['run']).resolve()
            if not run.is_relative_to((data_root/'runs').resolve()):raise ValueError('Run must be inside owned runtime root')
            verify_run(run)
            for parent in [destination/'demo-data',destination/'demo-data'/name]:
                if parent.is_symlink(): raise ValueError('Unsafe demo directory')
            for member in ['result.json','clip.mp4']:copy_file(run/member,destination/'demo-data'/name/member)
            public['clips'].append({'id':name,'title':item['title'],'review_note':item.get('review_note',''),'result':f'demo-data/{name}/result.json','video':f'demo-data/{name}/clip.mp4'})
        (destination/'demo-data/catalog.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    return destination


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    """Single HTTP byte ranges support seeks without sending the entire video."""
    def list_directory(self, path):
        self.send_error(403,'Directory listing disabled'); return None

    def send_head(self):
        self._range=None
        path=Path(self.translate_path(self.path))
        if not path.resolve().is_relative_to(Path(self.directory).resolve()):
            self.send_error(403);return None
        header=self.headers.get('Range')
        if not header or not path.is_file():return super().send_head()
        size=path.stat().st_size
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
        try:
            if not match or not any(match.groups()):raise ValueError()
            a,b=match.groups()
            if a:start=int(a);end=min(int(b),size-1) if b else size-1
            else:
                suffix=int(b)
                if suffix<=0:raise ValueError()
                start=max(0,size-suffix);end=size-1
            if not 0<=start<=end<size:raise ValueError()
        except ValueError:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return None
        stream=path.open('rb');stream.seek(start);self._range=(start,end)
        self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Accept-Ranges','bytes');self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length',str(end-start+1));self.end_headers();return stream

    def end_headers(self):
        self.send_header('Cache-Control','no-cache')
        super().end_headers()

    def copyfile(self, source, outputfile):
        try:
            if self._range is None:return super().copyfile(source,outputfile)
            remaining=self._range[1]-self._range[0]+1
            while remaining:
                block=source.read(min(65536,remaining))
                if not block:break
                outputfile.write(block);remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError):
            pass  # Browser cancelled a seek; this is not a corrupt run.


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8031);parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();project=Path(__file__).resolve().parents[1]
    data_root=Path(os.environ.get('LABPRISM_DATA_ROOT',str(Path.home()/'.local/share/labprism'))).resolve()
    directory=prepare(project,data_root)
    if args.prepare_only:print(directory);return
    handler=functools.partial(PreviewHandler,directory=str(directory))
    with http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
        print(f'LabPrism local preview: http://127.0.0.1:{args.port}/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass

if __name__=='__main__':main()
