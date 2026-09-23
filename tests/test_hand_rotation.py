import numpy as np
import pytest
from labprism.perception.hand_rotation import select_orientation
from labprism.evaluation import match_localization


def estimate(x,score,turn):
    return {'points':[[x,10.] for _ in range(21)],'scores':[score]*21,
            'turns':turn,'selection_score':score}


def test_single_confident_geometric_outlier_does_not_win_consensus():
    variants=[estimate(10.,.6,0),estimate(11.,.7,1),estimate(12.,.65,2),estimate(90.,.95,3)]
    assert select_orientation(variants,[0,0,100,100])['turns']==3
    selected=select_orientation(variants,[0,0,100,100],'consensus')
    assert selected['turns']==1
    assert selected['points']==variants[1]['points']  # Observed orientation, not fabricated mean.
    assert all('agreement_error' not in p for p in variants)


def test_unsupported_orientations_cannot_create_agreement():
    variants=[estimate(10.,.1,0),estimate(11.,.2,1),estimate(80.,.8,2)]
    selected=select_orientation(variants,[0,0,100,100],'consensus')
    assert selected['turns']==2 and selected['selection_method']=='score_fallback_no_consensus'
    variants[1]['points'][0][0]=np.nan
    assert select_orientation(variants,[0,0,100,100],'consensus')['turns']==2
    with pytest.raises(ValueError):select_orientation(variants,[0,0,100,100],'unknown')


def test_overlapping_hands_cannot_lose_a_qualified_match_to_subthreshold_pair():
    truth=[[50,0,150,100],[83,0,183,100]]
    predictions=[[50,0,150,100],[17,0,117,100]]
    assert match_localization(truth,predictions)=={0:1,1:0}
    assert match_localization(truth,[])=={}
    assert match_localization([],predictions)=={}
