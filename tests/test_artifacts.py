import json
import pytest
from labprism.artifacts import sha256, verify_media, receive_media, verify_run, verify_release

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


@pytest.fixture
def stored_run(tmp_path):
    run=tmp_path/'run';run.mkdir();(run/'evidence').mkdir()
    (run/'clip.mp4').write_bytes(b'video fixture')
    (run/'evidence/frame.jpg').write_bytes(b'evidence fixture')
    producer={'source_sha256':'a'*64,'split':'train','camera_role':'first_person','parent_start_seconds':0,'files':{'clip.mp4':sha256(run/'clip.mp4')}}
    model={'id':'fixture','sha256':'b'*64}
    result={'schema_version':'labprism-video-result/1','source':dict(producer,clip_sha256=producer['files']['clip.mp4']),
            'models':[model],'video':{'width':10,'height':10,'duration_ms':100,'coordinate_system':'clip_pixels_top_left_xy'},
            'frames':[{'frame_index':0,'timestamp_ms':0,'source_timestamp_ms':0,'objects':[],'hands':[]}]}
    for name, value in [('producer-receipt.json',producer),('result.json',result),('model-receipt.json',{'models':[model]})]:
        (run/name).write_text(json.dumps(value))
    receipt={'schema_version':'labprism-inference-run/1','source_sha256':'a'*64,'model_receipt_sha256':sha256(run/'model-receipt.json'),
             'files':{p.name:sha256(p) for p in run.iterdir() if p.is_file()},'evidence':{'frame.jpg':sha256(run/'evidence/frame.jpg')}}
    (run/'receipt.json').write_text(json.dumps(receipt))
    return run


def test_complete_run_receipt(stored_run):
    assert verify_run(stored_run)['source']['camera_role']=='first_person'


@pytest.mark.parametrize('change',['evidence','producer','model','missing','traversal'])
def test_run_refuses_inconsistent_evidence(stored_run,change):
    run=stored_run;r=json.loads((run/'receipt.json').read_text())
    if change=='evidence':(run/'evidence/frame.jpg').write_bytes(b'corrupt')
    if change in {'producer','model'}:
        name='producer-receipt.json' if change=='producer' else 'model-receipt.json'
        data=json.loads((run/name).read_text())
        if change=='producer':data['camera_role']='third_person'
        else:data['models'][0]['sha256']='c'*64
        (run/name).write_text(json.dumps(data));r['files'][name]=sha256(run/name)
        if change=='model':r['model_receipt_sha256']=sha256(run/name)
    if change=='missing':del r['files']['producer-receipt.json']
    if change=='traversal':r['evidence']['../clip.mp4']=r['files']['clip.mp4']
    (run/'receipt.json').write_text(json.dumps(r))
    with pytest.raises(ValueError):verify_run(run)


@pytest.mark.parametrize('change',[None,'manifest','bytes','traversal','symlink'])
def test_release_integrity(tmp_path,change):
    root=tmp_path/'release';root.mkdir();(root/'media').write_bytes(b'media fixture')
    receipt={'files':{'media':{'sha256':sha256(root/'media'),'bytes':13}}}
    if change=='traversal':receipt['files']['../external']=receipt['files'].pop('media')
    (root/'release.json').write_text(json.dumps(receipt))
    (root/'READY.json').write_text(json.dumps({'release_sha256':sha256(root/'release.json')}))
    if change=='manifest':(root/'release.json').write_text('{}')
    if change=='bytes':(root/'media').write_bytes(b'corrupt')
    if change=='symlink':
        (tmp_path/'external').write_bytes((root/'media').read_bytes());(root/'media').unlink();(root/'media').symlink_to(tmp_path/'external')
    if change is None:assert verify_release(root)==receipt
    else:
        with pytest.raises(ValueError):verify_release(root)
