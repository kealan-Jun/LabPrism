import numpy as np
import pytest

from labprism.tracking.appearance import AppearanceTracker, CameraMotion


def obj(box,label='beaker'):
    return {'box':list(box),'label':label,'confidence':.9}


def test_appearance_preserves_identity_when_objects_move_within_camera():
    tracker=AppearanceTracker()
    image=np.zeros((80,160,3),np.uint8)
    image[20:50,20:50]=[0,0,255];image[20:50,55:85]=[255,0,0]
    first=tracker.update([obj([20,20,50,50]),obj([55,20,85,50])],0,image)
    moved=np.zeros_like(image)
    moved[20:50,30:60]=[0,0,255];moved[20:50,70:100]=[255,0,0]
    second=tracker.update([obj([30,20,60,50]),obj([70,20,100,50])],100,moved)
    assert second[0]['track_id']==first[0]['track_id']
    assert second[1]['track_id']==first[1]['track_id']


def test_camera_transform_recovery_emits_no_gap_boxes_and_expires():
    tracker=AppearanceTracker(max_gap_ms=1000)
    image=np.full((100,200,3),180,np.uint8)
    first=tracker.update([obj([10,10,30,30])],0,image)[0]['track_id']
    affine=np.array([[1.,0.,60.],[0.,1.,0.]])
    assert tracker.update([],100,image,affine)==[]
    second=tracker.update([obj([70,10,90,30])],300,image)[0]
    assert second['track_id']==first
    assert second['track_state']=='reassociated_after_gap'
    assert len(second['trail'])==2
    assert tracker.update([obj([70,10,90,30])],1500,image)[0]['track_id']!=first
    with pytest.raises(ValueError):tracker.update([],1500,image)


def test_identical_location_with_incompatible_appearance_is_not_same_identity():
    tracker=AppearanceTracker()
    red=np.zeros((80,80,3),np.uint8);red[:]=[0,0,255]
    blue=np.zeros_like(red);blue[:]=[255,0,0]
    first=tracker.update([obj([20,20,50,50])],0,red)[0]['track_id']
    assert tracker.update([obj([20,20,50,50])],100,blue)[0]['track_id']!=first


def test_global_motion_is_measured_on_pixels_and_rejects_blank_frames():
    import cv2
    rng=np.random.default_rng(42)
    image=rng.integers(0,256,(240,320,3),dtype=np.uint8)
    moved=cv2.warpAffine(image,np.array([[1.,0.,8.],[0.,1.,4.]]),(320,240))
    estimator=CameraMotion();estimator.update(image,[])
    affine,report=estimator.update(moved,[])
    assert report['status']=='estimated'
    assert np.allclose(affine[:,2],[8,4],atol=1)
    estimator=CameraMotion();blank=np.zeros_like(image);estimator.update(blank,[])
    assert estimator.update(blank,[])[1]['status']=='insufficient_features'
