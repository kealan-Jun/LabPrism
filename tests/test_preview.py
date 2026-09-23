import functools
import http.client
import http.server
import importlib.util
from pathlib import Path
import threading
import pytest

spec=importlib.util.spec_from_file_location('preview',Path(__file__).parents[1]/'scripts/preview_website.py');preview=importlib.util.module_from_spec(spec);spec.loader.exec_module(preview)
@pytest.fixture
def server(tmp_path):
    (tmp_path/'video.mp4').write_bytes(bytes(range(100)))
    handler=functools.partial(preview.PreviewHandler,directory=str(tmp_path))
    s=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler);t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
    yield s.server_port
    s.shutdown();s.server_close();t.join()

@pytest.mark.parametrize('range_header,status,body',[('bytes=20-29',206,bytes(range(20,30))),('bytes=-3',206,bytes(range(97,100))),('bytes=97-',206,bytes(range(97,100))),('bytes=100-',416,b''),('bytes=2-1',416,b''),('bytes=0-1,4-5',416,b''),('bytes=-0',416,b'')])
def test_video_seek_ranges(server,range_header,status,body):
    c=http.client.HTTPConnection('127.0.0.1',server);c.request('GET','/video.mp4',headers={'Range':range_header});r=c.getresponse()
    assert r.status==status;assert r.read()==body;c.close()

def test_no_directory_listing(server):
    c=http.client.HTTPConnection('127.0.0.1',server);c.request('GET','/');r=c.getresponse();assert r.status==403;c.close()


@pytest.mark.parametrize('headers', [
    {'Host': 'attacker.invalid', 'Origin': 'http://attacker.invalid'},
    {'Origin': 'https://external.example'},
    {},
])
def test_analysis_mutations_reject_cross_origin_and_missing_origin(server, headers):
    c=http.client.HTTPConnection('127.0.0.1',server)
    c.request('POST','/api/analysis','{}',headers=headers)
    response=c.getresponse()
    assert response.status==403
    response.read();c.close()


def test_reject_dns_rebinding_host_on_read(server):
    c=http.client.HTTPConnection('127.0.0.1',server)
    c.request('GET','/video.mp4',headers={'Host':'external.example'})
    response=c.getresponse();assert response.status==403
    response.read();c.close()
