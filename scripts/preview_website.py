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
import subprocess
import sys
import urllib.parse
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from labprism.artifacts import sha256, verify_run
from labprism.result_chunks import write_chunks
from labprism.runtime.jobs import Jobs, MAX_UPLOAD, write_json
from labprism.inspection_preview import inspection_assets


def copy_file(source, destination):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('Preview files cannot be symlinks')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def story_assets(data_root, nas_root):
    """Expose only receipt-verified website files; keep new media on NAS."""
    manifest_path = data_root / 'receipts/record-story.json'
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text())
    root = Path(manifest['snapshot'])
    if root.is_symlink() or not root.resolve().is_relative_to((nas_root / 'media/website').resolve()):
        raise ValueError('Record story outside owned NAS website assets')
    if sha256(root / 'receipt.json') != manifest['receipt_sha256']:
        raise ValueError('Record story receipt hash changed')
    receipt = json.loads((root / 'receipt.json').read_text())
    if receipt.get('mode') != 'verified_producer_archive':
        raise ValueError('Record story requires real producer archives')
    assets = {}
    for name, digest in receipt['files'].items():
        if not re.fullmatch(r'(catalog\.json|(?:period-[a-z0-9-]+/)?(?:story\.json|[a-z0-9-]+\.(mp4|jpg|png|opus)))', name):
            raise ValueError('Invalid record story asset')
        path = root / name
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError('Record story asset hash changed')
        stat = path.stat()
        assets['/record-story/' + name] = (path, stat.st_size, stat.st_mtime_ns)
    return assets


def prepare_showcase(data_root, destination):
    manifest_path = data_root / 'receipts/website-showcase.json'
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text())
    root = Path(manifest['snapshot']).resolve()
    if not root.is_relative_to((data_root / 'media/website').resolve()):
        raise ValueError('Showcase outside owned website assets')
    if sha256(root / 'receipt.json') != manifest['receipt_sha256']:
        raise ValueError('Showcase receipt changed')
    receipt = json.loads((root / 'receipt.json').read_text())
    if receipt.get('mode') != 'real_verified_inference_stills':
        raise ValueError('Showcase must contain verified real inference frames')
    # Validate the entire bundle before making any of it available to the browser.
    for name, digest in receipt['files'].items():
        if not re.fullmatch(r'(showcase\.json|[a-z0-9-]+\.jpg)', name) or sha256(root / name) != digest:
            raise ValueError('Invalid showcase file or hash')
    if (destination / 'showcase').is_symlink():
        raise ValueError('Unsafe showcase directory')
    for name in receipt['files']:
        copy_file(root / name, destination / 'showcase' / name)


def publish_run(item, data_root, destination):
    name=item['id']
    if not re.fullmatch(r'[a-z0-9-]+',name): raise ValueError('Unsafe demo ID')
    run=Path(item['run']).resolve()
    if not run.is_relative_to((data_root/'runs').resolve()):raise ValueError('Run must be inside owned runtime root')
    result = verify_run(run)
    for parent in [destination/'demo-data',destination/'demo-data'/name]:
        if parent.is_symlink(): raise ValueError('Unsafe demo directory')
    copy_file(run/'clip.mp4',destination/'demo-data'/name/'clip.mp4')
    for frame in result['frames']:
        for observation in frame.get('ocr_observations', []):
            filename=observation['image_file']
            if not re.fullmatch(r'ocr-[a-f0-9]{64}\.png',filename):raise ValueError('Unsafe video OCR crop')
            copy_file(run/filename,destination/'demo-data'/name/filename)
    write_chunks(result, destination/'demo-data'/name)
    return {'id':name,'title':item['title'],'review_note':item.get('review_note',''),'result':f'demo-data/{name}/index.json','download':f'demo-data/{name}/result.json','video':f'demo-data/{name}/clip.mp4',
        'source_sha256':result['source']['source_sha256'],'clip_sha256':result['source']['clip_sha256'],
        'experiment':result['source'].get('experiment',{}).get('experiment_id'),
        'camera_id':result['source']['camera_id'],'camera_role':result['source']['camera_role'],
        'width':result['video']['width'],'height':result['video']['height']}


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
    prepare_showcase(data_root, destination)
    catalog_path=data_root/'receipts/demo-catalog.json'
    if catalog_path.exists():
        catalog=json.loads(catalog_path.read_text()); public={'schema_version':'labprism-demo-catalog/1','clips':[]}
        for item in catalog['clips']:
            public['clips'].append(publish_run(item, data_root, destination))
        (destination/'demo-data/catalog.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    settings=json.loads((project/'configs/project.json').read_text())
    _,inspection_clips=inspection_assets(data_root,Path(os.environ.get('LABPRISM_NAS_ROOT',settings['nas_root_default'])),settings['nas_volume_id'])
    if inspection_clips:
        catalog_file=destination/'demo-data/catalog.json'
        public=json.loads(catalog_file.read_text()) if catalog_file.exists() else {'schema_version':'labprism-demo-catalog/1','clips':[]}
        ids={c['id'] for c in inspection_clips}
        public['clips']=[c for c in public['clips'] if c['id'] not in ids]+inspection_clips
        write_json(catalog_file,public)
    integration = data_root/'receipts/upstream-catalog.json'
    if integration.exists():
        manifest=json.loads(integration.read_text());root=Path(manifest['snapshot']).resolve()
        if not root.is_relative_to((data_root/'imports').resolve()):raise ValueError('Snapshot outside owned imports')
        receipt=json.loads((root/'receipt.json').read_text())
        if receipt['mode']!='real_api':raise ValueError('Default product cannot use fixtures')
        for name,digest in receipt['files'].items():
            if Path(name).name!=name or sha256(root/name)!=digest:raise ValueError('Upstream snapshot hash mismatch')
        # The product consumes only the normalized snapshot and hash-verified images.
        for name in receipt['files']:
            if name=='snapshot.json' or name.endswith('.png'):copy_file(root/name,destination/'upstream'/name)
    multiview = data_root/'receipts/multiview-catalog.json'
    if multiview.exists():
        manifest=json.loads(multiview.read_text());root=Path(manifest['snapshot']).resolve()
        if not root.is_relative_to((data_root/'imports').resolve()):raise ValueError('Multiview outside owned imports')
        receipt=json.loads((root/'receipt.json').read_text())
        if receipt.get('mode')!='real_api_and_received_media':raise ValueError('Multiview requires real sources')
        if sha256(root/'receipt.json')!=manifest['receipt_sha256']:raise ValueError('Multiview receipt changed')
        for name,digest in receipt['files'].items():
            if Path(name).name!=name or sha256(root/name)!=digest:raise ValueError('Multiview file/hash mismatch')
        for name in receipt['files']:
            if name=='snapshot.json' or re.fullmatch(r'view-\d+\.mp4',name):copy_file(root/name,destination/'multiview'/name)
    diagnostic = data_root/'receipts/ocr-diagnostic-catalog.json'
    if diagnostic.exists():
        manifest=json.loads(diagnostic.read_text());root=Path(manifest['snapshot']).resolve()
        if not root.is_relative_to((data_root/'imports').resolve()):raise ValueError('OCR diagnostic outside owned imports')
        receipt=json.loads((root/'receipt.json').read_text())
        if receipt.get('mode')!='real_producer_diagnostic' or sha256(root/'receipt.json')!=manifest['receipt_sha256']:
            raise ValueError('OCR diagnostic receipt differs')
        for name,digest in receipt['files'].items():
            if Path(name).name!=name or sha256(root/name)!=digest:raise ValueError('OCR diagnostic hash mismatch')
        for name in receipt['files']:
            if name=='snapshot.json' or re.fullmatch(r'[a-f0-9]{64}\.png',name):copy_file(root/name,destination/'ocr-diagnostic'/name)
    return destination


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    """Single HTTP byte ranges support seeks without sending the entire video."""
    def json_response(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def local_request(self, mutation=False):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        return self.headers.get('Host') in hosts and (not mutation or
            self.headers.get('Origin') == f'http://{self.headers.get("Host")}')

    def do_GET(self):
        if not self.local_request():
            self.send_error(403)
            return
        if self.path == '/api/analysis':
            jobs = self.server.analysis_jobs
            try:
                jobs.settings()
                available, error = True, None
            except (OSError, ValueError, KeyError) as exc:
                available, error = False, str(exc)
            self.json_response(200, {'available': available, 'error': error,
                                    'sources': jobs.sources(), 'jobs': jobs.list()})
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.local_request():
            self.send_error(403)
            return
        super().do_HEAD()

    def translate_path(self, path):
        key = urllib.parse.urlsplit(path).path
        asset = getattr(self.server, 'story_assets', {}).get(key)
        return str(asset[0]) if asset else super().translate_path(path)

    def do_POST(self):
        self.close_connection = True
        if not self.local_request(mutation=True):
            self.json_response(403, {'error': '仅允许当前本地页面提交分析'})
            return
        try:
            jobs = self.server.analysis_jobs
            self.connection.settimeout(60)
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('需要明确的视频文件长度')
            length = int(self.headers.get('Content-Length', '0'))
            if self.path == '/api/analysis/upload':
                if self.headers.get('Content-Type') != 'video/mp4' or not 0 < length <= MAX_UPLOAD:
                    raise ValueError('仅支持不超过 1 GiB 的 MP4 文件')
                metadata = json.loads(urllib.parse.unquote(self.headers.get('X-Video-Metadata', '')))
                created = jobs.accept_upload(self.rfile, length, metadata)
            elif self.path == '/api/analysis' or re.fullmatch(r'/api/analysis/analysis-[a-f0-9]{32}/retry', self.path):
                if not 0 < length <= 4096:
                    raise ValueError('无效分析请求')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('请求必须为 JSON 对象')
                created = jobs.submit(body['source_id']) if self.path == '/api/analysis' else jobs.retry(self.path.split('/')[3])
            else:
                self.json_response(404, {'error': '没有此分析操作'})
                return
            self.json_response(202, created)
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            self.json_response(400, {'error': str(error)[:400]})

    def list_directory(self, path):
        self.send_error(403,'Directory listing disabled'); return None

    def send_head(self):
        self._range=None
        path=Path(self.translate_path(self.path))
        key = urllib.parse.urlsplit(self.path).path
        asset = getattr(self.server, 'story_assets', {}).get(key)
        if key.startswith(('/record-story/','/inspection/')) and not asset:
            self.send_error(404); return None
        if asset:
            try:
                stat = path.stat()
                unchanged = (not path.is_symlink() and stat.st_size == asset[1] and stat.st_mtime_ns == asset[2])
            except OSError:
                unchanged = False
            if not unchanged:
                self.send_error(409, 'Verified asset changed'); return None
        elif not path.resolve().is_relative_to(Path(self.directory).resolve()):
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
        server.story_assets = story_assets(data_root, Path(os.environ.get('LABPRISM_NAS_ROOT', '/mnt/realityloop-nas/LabPrism')))
        settings=json.loads((project/'configs/project.json').read_text())
        server.story_assets.update(inspection_assets(data_root,Path(os.environ.get('LABPRISM_NAS_ROOT',settings['nas_root_default'])),settings['nas_volume_id'])[0])
        def publish(item):
            public_item = publish_run(item, data_root, directory)
            # One GPU worker owns publication; atomic files keep readers from
            # seeing a half-written catalog. Only verified finished runs appear.
            for path, entry in [(data_root/'receipts/demo-catalog.json', item),
                                (directory/'demo-data/catalog.json', public_item)]:
                catalog = json.loads(path.read_text()) if path.exists() else {'schema_version':'labprism-demo-catalog/1','clips':[]}
                catalog['clips'] = [c for c in catalog['clips'] if c['id'] != item['id']] + [entry]
                write_json(path, catalog)
        server.analysis_jobs = Jobs(data_root, project, publish)
        print(f'LabPrism local preview: http://127.0.0.1:{args.port}/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass

if __name__=='__main__':main()
