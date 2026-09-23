import numpy as np
import pytest
from labprism.perception.trained_segmentation import letterbox_rgb,restore_mask,JointSegmenter


def test_letterbox_roundtrip_preserves_native_size_and_holes():
    pytest.importorskip('cv2');pytest.importorskip('PIL')
    rgb=np.zeros((40,80,3),np.uint8)
    image,t=letterbox_rgb(rgb,80)
    assert image.shape==(80,80,3) and t['top']==20 and t['left']==0
    assert np.all(image[:20]==114)
    mask=np.zeros((80,80),np.uint8);mask[30:50,20:60]=1;mask[35:45,35:45]=0
    restored=restore_mask(mask,t)
    assert restored.shape==(40,80) and restored[11,21]==1 and restored[20,40]==0


def test_role_and_identity_fail_before_model_execution(tmp_path):
    with pytest.raises(ValueError,match='role'):
        JointSegmenter(tmp_path/'missing.pt','0'*64,'first_person','third_person')
    p=tmp_path/'candidate.pt';p.write_bytes(b'not a model')
    with pytest.raises(ValueError,match='hash'):
        JointSegmenter(p,'0'*64,'first_person','first_person')


def test_native_logits_keep_holes_and_crop_to_original_boxes():
    torch=pytest.importorskip('torch');pytest.importorskip('ultralytics')
    from labprism.perception.trained_segmentation import restore_mask_logits
    t={'width':80,'height':40,'size':80,'nw':80,'nh':40,'left':0,'top':20}
    logits=torch.full((1,8,8),5.);logits[:,3:5,3:5]=-5.
    masks=restore_mask_logits(logits,torch.tensor([[10.,0.,70.,40.]]),t)
    assert tuple(masks.shape)==(1,40,80)
    assert masks[0,20,40]==0 and masks[0,5,20]==1
    assert not masks[:,:,:10].any() and not masks[:,:,70:].any()
    empty=restore_mask_logits(torch.empty(0,8,8),torch.empty(0,4),t)
    assert tuple(empty.shape)==(0,40,80)
    with pytest.raises(ValueError,match='Nonfinite'):
        restore_mask_logits(logits*float('nan'),torch.zeros(1,4),t)
    with pytest.raises(ValueError,match='matching'):
        restore_mask_logits(logits,torch.zeros(2,4),t)


def test_resolution_and_decode_policy_fail_before_loading_weights(tmp_path):
    for value in [639,0,1296,True]:
        with pytest.raises(ValueError,match='Input size'):
            JointSegmenter(tmp_path/'missing',None,'first_person','first_person',imgsz=value)
    with pytest.raises(ValueError,match='decoding'):
        JointSegmenter(tmp_path/'missing',None,'first_person','first_person',mask_decode='invented')
