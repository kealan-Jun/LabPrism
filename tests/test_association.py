import copy
import pytest
from labprism.tracking.association import Tracker, reject_screen_conflicts, deduplicate_hands


def obj(box=(0,0,20,20),label='beaker',confidence=.9):return {'box':list(box),'label':label,'confidence':confidence}


def test_gaps_do_not_hallucinate_and_expired_identity_is_not_reused():
    tracker=Tracker();first=tracker.update([obj()],0)[0]['track_id']
    assert tracker.update([],100)==[]
    resumed=tracker.update([obj()],300)[0]
    assert resumed['track_id']==first and resumed['track_state']=='reassociated_after_gap'
    assert tracker.update([obj()],1000)[0]['track_id']!=first


def test_unique_assignments_and_class_gating():
    tracker=Tracker();previous=tracker.update([obj(),obj((25,0,45,20))],0)
    current=tracker.update([obj((2,0,22,20)),obj((24,0,44,20)),obj(label='bottle')],100)
    assert current[0]['track_id']==previous[0]['track_id']
    assert current[1]['track_id']==previous[1]['track_id']
    assert len({o['track_id'] for o in current})==3
    with pytest.raises(ValueError):tracker.update([],100)


def test_screen_veto_needs_positive_model_evidence_and_preserves_scale():
    scale=obj(label='balance');screen=obj((40,0,60,20),label='balance')
    context=[obj((38,0,65,30),label='laptop',confidence=.85)]
    before=copy.deepcopy(screen)
    kept,rejected=reject_screen_conflicts([scale,screen],context)
    assert kept==[scale] and rejected[0]['box']==screen['box'] and screen==before
    assert reject_screen_conflicts([screen],[obj((38,0,65,30),label='laptop',confidence=.2)])[0]==[screen]
    assert reject_screen_conflicts([screen],[])[0]==[screen]


def test_duplicate_hand_proposals_do_not_create_extra_skeletons():
    hands=[obj(label='hand'),obj((1,0,21,20),label='gloved_hand',confidence=.8),obj((30,0,50,20),label='gloved_hand')]
    assert len(deduplicate_hands(hands))==2
