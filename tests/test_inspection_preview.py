import hashlib,json,functools,http.client,http.server,threading
import pytest
from labprism.inspection_preview import inspection_assets
from test_preview import preview


def bundle(tmp_path,monkeypatch):
    nas=tmp_path/'nas';root=nas/'media/inspection/test';root.mkdir(parents=True)
    (nas/'.labprism-volume.json').write_text(json.dumps({'volume_id':'expected'}))
    monkeypatch.setattr('labprism.inspection_preview.subprocess.check_output',lambda *a,**kw:json.dumps({'filesystems':[{'fstype':'cifs'}]}))
    run=root/'candidate';run.mkdir();(run/'clip.mp4').write_bytes(bytes(range(100)))
    (run/'index.json').write_text('{}');(run/'result.json').write_text('{}')
    (root/'catalog.json').write_text(json.dumps({'clips':[{'id':'candidate','video':'inspection/candidate/clip.mp4','result':'inspection/candidate/index.json','download':'inspection/candidate/result.json'}]}))
    (root/'receipt.json').write_text(json.dumps({'schema_version':'labprism-inspection-preview/1','files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}}))
    data=tmp_path/'data';(data/'receipts').mkdir(parents=True);(data/'receipts/inspection-preview.json').write_text(json.dumps({'snapshot':str(root),'receipt_sha256':hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest()}))
    return data,nas,root


def test_rejects_changed_volume_and_media(tmp_path,monkeypatch):
    data,nas,root=bundle(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='identity'):inspection_assets(data,nas,'wrong')
    (root/'candidate/clip.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):inspection_assets(data,nas,'expected')


def test_only_receipted_inspection_assets_are_served(tmp_path,monkeypatch):
    data,nas,root=bundle(tmp_path,monkeypatch);assets,clips=inspection_assets(data,nas,'expected')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(preview.PreviewHandler,directory=str(data)));server.story_assets=assets
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for path,status in [('/inspection/candidate/clip.mp4',206),('/inspection/receipt.json',404),('/inspection/../receipt.json',404),('/inspection/%2e%2e/receipt.json',404)]:
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET',path,headers={'Range':'bytes=10-19'});r=c.getresponse();assert r.status==status;body=r.read()
            if status==206:assert body==bytes(range(10,20))
            c.close()
        (root/'candidate/clip.mp4').write_bytes(b'changed')
        c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET','/inspection/candidate/clip.mp4');r=c.getresponse();assert r.status==409;r.read();c.close()
    finally:server.shutdown();server.server_close();thread.join()
