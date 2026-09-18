import copy

from labprism.understanding.proximity import relations_for_frame, build_events


def frame(index, hand_x=15, score=.9):
    value={'frame_index':index,'timestamp_ms':index*200,'objects':[
        {'id':f'o{index}','label':'beaker','box':[20,0,40,20],'track_id':'object-1'}],
        'hands':[{'id':f'h{index}','track_id':'hand-1','points':[[hand_x,10,None]]*21,
                  'point_scores':[score]*21,'keypoint_threshold':.3}]}
    value['relations']=relations_for_frame(value)
    return value


def test_events_require_sustained_observations_and_never_claim_contact():
    frames=[frame(i) for i in range(4)]
    events=build_events(frames)
    assert len(events)==1
    assert (events[0]['start_ms'],events[0]['end_ms'])==(0,600)
    assert events[0]['physical_contact'] is None and events[0]['step'] is None
    assert len(events[0]['evidence'])==4
    assert build_events(frames[:3])==[]


def test_missing_or_low_score_fingertips_do_not_bridge_an_interval():
    assert frame(0,score=.2)['relations']==[]
    assert frame(0,hand_x=100)['relations']==[]
    frames=[frame(i) for i in range(7)]
    frames[3]['relations']=[]
    assert build_events(frames)==[]
    frames=[frame(i) for i in [0,1,2,10,11,12]]
    assert build_events(frames)==[]


def test_identity_switch_starts_a_new_interval():
    frames=[frame(i) for i in range(6)]
    for f in frames[3:]:
        f['relations'][0]['object_track_id']='another-object'
    assert build_events(frames)==[]
