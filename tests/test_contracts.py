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
