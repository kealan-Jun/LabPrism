import hashlib
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.parametrize('mismatch', ['pixels', 'time', 'dimensions'])
def test_service_replay_rejects_changed_decoder_evidence(monkeypatch, mismatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_service_detector import check_decoded_sample
    rgb=np.zeros((8,12,3),np.uint8)
    frame={'clip_pts':3072,'time_base':'1/15360','rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest()}
    check_decoded_sample(frame,rgb,200,[12,8])
    if mismatch=='pixels':rgb[0,0]=1
    if mismatch=='time':frame['clip_pts']=6144
    if mismatch=='dimensions':rgb=rgb.transpose(1,0,2)
    with pytest.raises(ValueError,match='Decoder pixels'):
        check_decoded_sample(frame,rgb,200,[12,8])
