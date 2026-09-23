import copy
import json
import numpy as np
import pytest
from labprism.contracts import validate_result
from labprism.geometry.transforms import rotation_matrix, transform_points, map_time
from labprism.result_chunks import write_chunks, browser_projection
from test_contracts import v3_result


def v4():
    r=v3_result();r['schema_version']='labprism-video-result/4';r['data_use']={'purpose':'production_observation'};r['source']['split']=None
    r['semantic_taxonomy']={'id':'lab-test','version':'1','classes':[{'id':201,'label':'surface'}],'unknown_id':0,'ignore_id':255}
    r['time_mapping']={'clip_origin_ms':0,'capture_origin_ms':None,'global_origin_ms':None}
    r['coordinates']={'clip_to_source':np.eye(3).tolist(),'operations':[]}
    r['output_statuses']={k:{'state':'not_run','reason':'test fixture'} for k in ['boxes','instance_masks','semantic_map','keypoints','tracks','relations','events','readouts']}
    for k in ['boxes','instance_masks','keypoints','tracks','relations']:
        r['output_statuses'][k]['state']='predicted'
    r['frames'][0].update(clip_pts=0,time_base='1001/30000')
    return r


def test_production_split_and_taxonomy_are_independent():
    r=v4();validate_result(r)
    r['source']['split']='train'
    with pytest.raises(ValueError):validate_result(r)
    r['data_use']['purpose']='evaluation';r['source']['split']='test';validate_result(r)
    r['data_use']['purpose']='development'
    with pytest.raises(ValueError):validate_result(r)


def test_custom_taxonomy_and_pts_validation():
    r=v4();f=r['frames'][0];f['semantic_map']={'taxonomy':'lab-test','file':'semantic-0.png','sha256':'a'*64}
    r['output_statuses']['semantic_map']['state']='predicted'
    f['semantic_regions']=[{'class_id':201,'mean_score':.8,'mask_contours':[]}];validate_result(r)
    f['semantic_regions'][0]['class_id']=0
    with pytest.raises(ValueError):validate_result(r)
    f['semantic_regions'][0]['class_id']=201;f['clip_pts']=1
    with pytest.raises(ValueError):validate_result(r)


@pytest.mark.parametrize('task', ['boxes','instance_masks','keypoints','tracks','relations'])
def test_task_unavailability_cannot_hide_stale_payload(task):
    r=v4();r['output_statuses'][task]={'state':'failed','reason':'current module failed'}
    with pytest.raises(ValueError, match='contains output'):
        validate_result(r)


def test_variable_pts_not_nominal_fps_and_coordinate_roundtrip():
    a=map_time(3,'1001/30000',source_start_ms=6000);b=map_time(8,'1001/30000')
    assert a['clip_ms']==pytest.approx(100.1) and b['clip_ms']==pytest.approx(266.933333)
    points=np.array([[0,0],[123,85],[199,99]],dtype=float)
    # Crop → resize/letterbox → mirror, then recover original pixels.
    crop=np.array([[1,0,-20],[0,1,-10],[0,0,1]])
    resize=np.array([[2,0,0],[0,2,30],[0,0,1]])
    mirror=np.array([[-1,0,399],[0,1,0],[0,0,1]])
    matrix=mirror@resize@crop
    assert np.allclose(transform_points(transform_points(points,matrix),np.linalg.inv(matrix)),points)
    for turn in range(4):
        matrix=rotation_matrix(200,100,turn)
        assert np.allclose(transform_points(transform_points(points,matrix),np.linalg.inv(matrix)),points)


def test_chunk_limits_and_private_metadata_not_in_browser(tmp_path):
    r=v3_result();r.update(models=[{'id':'m','path':'/private/weights','producer_receipt':'/private/x'}],environment={})
    r['source']['source_path']='/private/video';r['source']['command']=['secret']
    r['frames']=[dict(copy.deepcopy(r['frames'][0]),frame_index=i,timestamp_ms=i*100,source_timestamp_ms=6000+i*100) for i in range(30)]
    index=write_chunks(r,tmp_path,seconds=1,max_frames=8)
    assert max(c['count'] for c in index['chunks'])<=8
    assert sum(c['count'] for c in index['chunks'])==30
    assert '/private' not in (tmp_path/'result.json').read_text()
    assert 'frames' not in index and len(list(tmp_path.glob('frames-*')))==4


def test_current_pose_identity_survives_projection_without_training_paths():
    r=v3_result()
    r['models']=[{'id':'trained','task':'hand_landmarks_candidate','parent_sha256':'a'*64,
                  'producer_receipt':'/private/receipt.json','path':'/private/model.onnx',
                  'pose_lineage':{'path':'/private/old-run','result_sha256':'b'*64,
                                  'receipt_sha256':'c'*64,'command':'/private/command'}}]
    r['configuration']={'trained_hand_replay':{'model_id':'trained','private_path':'/private/run'},'source':'/private/source'}
    projected=browser_projection(r)
    assert projected['model_usage']=={'hand_pose':'trained'}
    assert projected['models'][0]['parent_sha256']=='a'*64
    assert projected['models'][0]['pose_lineage']=={'result_sha256':'b'*64,'receipt_sha256':'c'*64}
    assert '/private' not in json.dumps(projected)
    assert 'configuration' not in projected


def test_long_event_index_is_bounded_and_complete_download_retains_evidence(tmp_path):
    r=v3_result();r.update(models=[],environment={})
    r['frames']=[dict(copy.deepcopy(r['frames'][0]),frame_index=i,timestamp_ms=i*100,source_timestamp_ms=6000+i*100) for i in range(4)]
    event={'type':'hand_object_proximity_2d','start_ms':0,'end_ms':300,
           'hand_track_id':'hand-1','object_track_id':'object-1','physical_contact':None,'step':None,
           'status':'unreviewed_geometric_proposal','evidence':[
               {'frame_index':f['frame_index'],'timestamp_ms':f['timestamp_ms'],
                **{k:f['relations'][0][k] for k in ('hand_id','object_id','keypoint_index','distance_px')}}
               for f in r['frames']]}
    r['events']=[dict(event,id=f'event-{i}') for i in range(2001)]
    index=write_chunks(r,tmp_path)
    assert index['event_count']==2001 and index['events_truncated']
    assert len(index['events'])==2000 and index['events'][0]['evidence_count']==4
    assert 'evidence' not in index['events'][0]
    full=json.loads((tmp_path/'result.json').read_text())
    assert len(full['events'])==2001 and len(full['events'][0]['evidence'])==4


def test_layer_flags_require_actual_outputs_not_merely_objects(tmp_path):
    r=v3_result();r.update(models=[],environment={'actual_execution_providers':{'detection':'PyTorch CPU'}})
    f=r['frames'][0];f['relations']=[];f['hands']=[]
    for obj in f['objects']:
        obj['mask_contours']=[];obj['track_id']=None;obj['trail']=[]
    index=write_chunks(r,tmp_path)
    assert index['layers']['masks'] is False
    assert index['layers']['trails'] is False
    assert index['layers']['hands'] is False
    assert index['environment']['actual_execution_providers']['detection']=='PyTorch CPU'


def test_legacy_per_frame_nonexecution_is_preserved_without_hiding_mixed_coverage():
    r=v3_result();r['models']=[]
    r['frames'][0]['availability']['hands']='not_run'
    assert 'keypoints' not in browser_projection(r).get('output_statuses',{})
    r['frames'][0]['hands']=[]
    projected=browser_projection(r)
    assert projected['output_statuses']['keypoints']['state']=='not_run'
    assert 'output_statuses' not in r
    other=copy.deepcopy(r['frames'][0]);other['availability']['hands']='predicted'
    r['frames'].append(other)
    assert 'keypoints' not in browser_projection(r).get('output_statuses',{})
