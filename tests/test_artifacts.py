import json
import pytest
from labprism.artifacts import sha256, verify_media, receive_media

@pytest.fixture
def bundle(tmp_path):
    folder=tmp_path/'producer';folder.mkdir();(folder/'clip.mp4').write_bytes(b'test fixture, not real video')
    receipt={'schema_version':'annotation-workbench-demo-media/1','split':'train','camera_role':'first_person','annotations_exported':False,'dataset_ownership_transferred':False,'files':{'clip.mp4':sha256(folder/'clip.mp4')}}
    (folder/'receipt.json').write_text(json.dumps(receipt));return folder,receipt

def test_roundtrip_and_no_overwrite(bundle,tmp_path):
    folder,r=bundle;receive_media(folder,tmp_path/'received');assert verify_media(tmp_path/'received')==r
    with pytest.raises(FileExistsError):receive_media(folder,tmp_path/'received')

@pytest.mark.parametrize('change',['corrupt','test','unknown','traversal','symlink','missing'])
def test_fail_closed(bundle,tmp_path,change):
    folder,r=bundle
    if change=='corrupt':(folder/'clip.mp4').write_bytes(b'changed')
    if change=='test':r['split']='test'
    if change=='unknown':r['camera_role']='unknown'
    if change=='traversal':r['files']['../external']='0'*64
    if change=='symlink':
        (tmp_path/'external').write_bytes((folder/'clip.mp4').read_bytes());(folder/'clip.mp4').unlink();(folder/'clip.mp4').symlink_to(tmp_path/'external')
    if change=='missing':r['files']={}
    (folder/'receipt.json').write_text(json.dumps(r))
    with pytest.raises(ValueError):receive_media(folder,tmp_path/'received')
    assert not (tmp_path/'received').exists()
