import copy
import pytest
from labprism.contracts import validate_result

def result():
    return {'schema_version':'labprism-video-result/1','source':{'split':'train','camera_role':'third_person','parent_start_seconds':6},'video':{'width':960,'height':600,'duration_ms':8000,'coordinate_system':'clip_pixels_top_left_xy'},'frames':[{'frame_index':0,'timestamp_ms':0,'source_timestamp_ms':6000,'objects':[{'id':'a','box':[0,0,10,10],'confidence':.8,'mask_contours':[[[0,0],[2,0],[2,2]]]}],'hands':[]}]}

def test_accepts_real_coordinate_contract():assert validate_result(result())['frames'][0]['source_timestamp_ms']==6000

@pytest.mark.parametrize('case',['duplicate_time','bad_lineage','outside_box','outside_mask','bad_hand','empty','sealed'])
def test_rejects_inconsistent_coordinates_and_time(case):
    r=result();f=r['frames'][0]
    if case=='duplicate_time':r['frames'].append(copy.deepcopy(f))
    if case=='bad_lineage':f['source_timestamp_ms']=0
    if case=='outside_box':f['objects'][0]['box']=[0,0,1000,10]
    if case=='outside_mask':f['objects'][0]['mask_contours'][0][0]=[-1,0]
    if case=='bad_hand':f['hands']=[{'points':[[0,0,0]]}]
    if case=='empty':r['frames']=[]
    if case=='sealed':r['source']['split']='test'
    with pytest.raises(ValueError):validate_result(r)


def test_2d_hand_does_not_fabricate_depth():
    r=result();r['schema_version']='labprism-video-result/2'
    hand={'points':[[1,2,None] for _ in range(21)],'depth_available':False,'point_scores':[.4]*21}
    r['frames'][0]['hands']=[hand]
    validate_result(r)
    hand['points'][0][2]=0
    with pytest.raises(ValueError):validate_result(r)


def test_future_trails_and_duplicate_identities_are_rejected():
    r=result();o=r['frames'][0]['objects'][0];o['track_id']='track-1';o['trail']=[[100,5,5]]
    with pytest.raises(ValueError):validate_result(r)
    o['trail']=[];other=copy.deepcopy(o);other['id']='b';r['frames'][0]['objects'].append(other)
    with pytest.raises(ValueError):validate_result(r)


@pytest.mark.parametrize('invalid',['path','class','contour','missing_map'])
def test_semantic_layer_requires_bound_map_and_valid_pixels(invalid):
    r=result();r['schema_version']='labprism-video-result/2';f=r['frames'][0]
    f['semantic_map']={'file':'semantic-000000.png','sha256':'a'*64,'taxonomy':'ADE20K-150'}
    f['semantic_regions']=[{'class_id':0,'label':'wall','mean_score':.8,'mask_contours':[[[0,0],[1,0],[1,1]]]}]
    validate_result(r)
    if invalid=='path':f['semantic_map']['file']='../secret.png'
    if invalid=='class':f['semantic_regions'][0]['class_id']=150
    if invalid=='contour':f['semantic_regions'][0]['mask_contours'][0][0]=[-1,0]
    if invalid=='missing_map':del f['semantic_map']
    with pytest.raises(ValueError):validate_result(r)
