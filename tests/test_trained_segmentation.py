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
