import hashlib
import json
import functools
import http.client
import http.server
import threading
from test_preview import preview
import pytest


def bundle(tmp_path):
    nas = tmp_path / 'nas'; root = nas / 'media/website/story'; root.mkdir(parents=True)
    (root / 'view-0.mp4').write_bytes(bytes(range(100)))
    (root / 'story.json').write_text('{}')
    receipt = {'mode': 'verified_producer_archive', 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}}
    (root / 'receipt.json').write_text(json.dumps(receipt))
    data = tmp_path / 'data'; (data / 'receipts').mkdir(parents=True)
    (data / 'receipts/record-story.json').write_text(json.dumps({'snapshot': str(root), 'receipt_sha256': hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest()}))
    return data, nas, root


def test_rejects_tampered_media_before_serving(tmp_path):
    data, nas, root = bundle(tmp_path)
    (root / 'view-0.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        preview.story_assets(data, nas)


def test_only_verified_nas_assets_have_range_access(tmp_path):
    data, nas, root = bundle(tmp_path)
    handler = functools.partial(preview.PreviewHandler, directory=str(data))
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), handler)
    server.story_assets = preview.story_assets(data,nas)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for path, expected in [('/record-story/view-0.mp4',206),('/record-story/receipt.json',404),('/record-story/../receipt.json',404),('/record-story/%2e%2e/receipt.json',404)]:
            client=http.client.HTTPConnection('127.0.0.1',server.server_port)
            client.request('GET',path,headers={'Range':'bytes=20-29'});response=client.getresponse()
            assert response.status == expected
            body=response.read()
            if expected==206: assert body==bytes(range(20,30))
            client.close()
        (root/'view-0.mp4').write_bytes(b'changed after verification')
        client=http.client.HTTPConnection('127.0.0.1',server.server_port);client.request('GET','/record-story/view-0.mp4')
        response=client.getresponse();assert response.status==409;response.read();client.close()
    finally:
        server.shutdown();server.server_close();thread.join()


def test_catalog_nested_assets_are_explicit_and_private_evidence_stays_private(tmp_path):
    data,nas,root=bundle(tmp_path)
    period=root/'period-bench';period.mkdir()
    (period/'view-0.mp4').write_bytes(b'new period')
    (period/'story.json').write_text('{}')
    (root/'catalog.json').write_text('{}')
    def set_files(files):
        (root/'receipt.json').write_text(json.dumps({'mode':'verified_producer_archive','files':files}))
        (data/'receipts/record-story.json').write_text(json.dumps({'snapshot':str(root),'receipt_sha256':hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest()}))
    set_files({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [period/'view-0.mp4',period/'story.json',root/'catalog.json']})
    assets=preview.story_assets(data,nas)
    assert set(assets)=={'/record-story/catalog.json','/record-story/period-bench/story.json','/record-story/period-bench/view-0.mp4'}
    for name in ['period-bench/../story.json','period-bench/producer.json','period-bench/receipt.json','period-bench/producer/view-0.mp4']:
        set_files({name:'0'*64})
        with pytest.raises(ValueError,match='Invalid'): preview.story_assets(data,nas)
    (period/'view-0.mp4').unlink();(period/'view-0.mp4').symlink_to(root/'view-0.mp4')
    set_files({'period-bench/view-0.mp4':hashlib.sha256((root/'view-0.mp4').read_bytes()).hexdigest()})
    with pytest.raises(ValueError,match='hash'): preview.story_assets(data,nas)
