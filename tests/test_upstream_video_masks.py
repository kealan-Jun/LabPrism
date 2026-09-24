import copy
import json

import numpy as np
from PIL import Image
import pytest

from labprism.artifacts import sha256
from labprism.tracking.upstream_video_masks import validate_handoff


@pytest.fixture
def bundle(tmp_path):
    source = {'camera_role': 'first_person', 'camera_id': 'camera-x', 'split': 'train', 'source_sha256': 'a'*64}
    frame = {'frame_index': 12, 'timestamp_ms': 400, 'clip_pts': 6144, 'time_base': '1/15360', 'rgb_sha256': 'b'*64}
    prompt = {'id': 'o1', 'label': 'beaker'}
    request = {'parent_result_sha256': 'c'*64, 'input_transform': {'encoding': 'JPEG', 'quality': 95, 'resize': False},
               'windows': [{'id': 0, 'frames': [frame], 'prompts': [prompt]}]}
    request_path = tmp_path/'request.json'
    request_path.write_text(json.dumps(request))
    output = tmp_path/'producer'
    output.mkdir()
    mask = output/'temporal-000012-00.png'
    Image.fromarray(np.ones((8, 12), dtype=np.uint8)).save(mask)
    instance = {'id': 'w0-object0', 'seed_frame_index': 12, 'seed_object_id': 'o1', 'label': 'beaker',
                'visible_pixels': 96, 'mask': {'file': mask.name, 'sha256': sha256(mask)}}
    model = {'checkpoint_sha256': 'd'*64}
    result = {'schema_version': 'visioncortex-temporal-mask-result/1', 'source': source,
              'parent_result_sha256': request['parent_result_sha256'], 'request_sha256': sha256(request_path),
              'dimensions': [12, 8], 'input_transform': request['input_transform'], 'model': model,
              'identity_across_windows': False, 'quality_status': 'unreviewed_model_proposals',
              'frames': [{**frame, 'window_id': 0, 'temporal_instances': [instance]}]}
    parent = {'source': source, 'video': {'width': 12, 'height': 8}, 'frames': [frame]}

    def write(value):
        (output/'result.json').write_text(json.dumps(value))
        receipt = {'schema_version': 'visioncortex-temporal-mask-receipt/1', 'request_sha256': sha256(request_path),
                   'files': {p.name: sha256(p) for p in output.iterdir() if p.name != 'receipt.json'}, 'model': model}
        (output/'receipt.json').write_text(json.dumps(receipt))
    write(result)
    return output, request_path, parent, result, write


def test_receive_exact_mask_and_source(bundle):
    output, request, parent, result, _ = bundle
    assert validate_handoff(output, request, parent) == result


@pytest.mark.parametrize('failure', ['time', 'missing', 'duplicate', 'seed', 'pixels', 'camera', 'quality', 'window'])
def test_reject_receipted_but_inconsistent_handoff(bundle, failure):
    output, request, parent, result, write = bundle
    result = copy.deepcopy(result)
    frame = result['frames'][0]
    if failure == 'time':
        frame['clip_pts'] += 1
    elif failure == 'missing':
        result['frames'] = []
    elif failure == 'duplicate':
        result['frames'].append(copy.deepcopy(frame))
    elif failure == 'seed':
        frame['temporal_instances'][0]['seed_frame_index'] = 18
    elif failure == 'pixels':
        frame['temporal_instances'][0]['visible_pixels'] = 95
    elif failure == 'camera':
        result['source']['camera_id'] = 'other'
    elif failure == 'quality':
        result['quality_status'] = 'ground_truth'
    elif failure == 'window':
        frame['window_id'] = 3
    write(result)
    with pytest.raises(ValueError):
        validate_handoff(output, request, parent)


def test_reject_tampered_raster(bundle):
    output, request, parent, _, _ = bundle
    (output/'temporal-000012-00.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='file changed'):
        validate_handoff(output, request, parent)


@pytest.mark.parametrize('changed', [None, 'request', 'result'])
def test_observation_purpose_survives_producer_boundary(bundle, changed):
    output, request_path, parent, result, write = bundle
    request = json.loads(request_path.read_text())
    purpose = {'purpose': 'production_observation'}
    request.update(schema_version='visioncortex-temporal-mask-request/2', data_use=purpose)
    parent['data_use'] = purpose
    result['data_use'] = purpose
    if changed == 'request':
        request['data_use'] = {'purpose': 'development'}
    if changed == 'result':
        result['data_use'] = {'purpose': 'development'}
    request_path.write_text(json.dumps(request))
    result['request_sha256'] = sha256(request_path)
    write(result)
    if changed:
        with pytest.raises(ValueError, match='purpose'):
            validate_handoff(output, request_path, parent)
    else:
        assert validate_handoff(output, request_path, parent)['data_use'] == purpose
