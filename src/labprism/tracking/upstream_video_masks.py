"""Validate producer mask identity before it enters an immutable replay."""
import json
from pathlib import Path

from labprism.artifacts import sha256


def validate_handoff(directory, request_path, parent):
    import numpy as np
    from PIL import Image

    directory = Path(directory)
    request = json.loads(Path(request_path).read_text())
    receipt = json.loads((directory / 'receipt.json').read_text())
    if (receipt.get('schema_version') != 'visioncortex-temporal-mask-receipt/1'
            or receipt.get('request_sha256') != sha256(request_path)
            or 'result.json' not in receipt.get('files', {})):
        raise ValueError('Unbound temporal producer receipt')
    for name, digest in receipt['files'].items():
        path = directory / name
        if Path(name).name != name or path.is_symlink() or sha256(path) != digest:
            raise ValueError('Temporal producer file changed')
    result = json.loads((directory / 'result.json').read_text())
    if request.get('schema_version') == 'visioncortex-temporal-mask-request/2':
        if (request.get('data_use') != parent.get('data_use')
                or result.get('data_use') != request.get('data_use')):
            raise ValueError('Temporal data purpose changed')
    if (result.get('schema_version') != 'visioncortex-temporal-mask-result/1'
            or result.get('source') != parent['source']
            or result.get('parent_result_sha256') != request['parent_result_sha256']
            or result.get('request_sha256') != sha256(request_path)
            or result.get('dimensions') != [parent['video']['width'], parent['video']['height']]
            or result.get('model') != receipt.get('model')
            or result.get('input_transform') != request['input_transform']
            or result.get('identity_across_windows') is not False
            or result.get('quality_status') != 'unreviewed_model_proposals'):
        raise ValueError('Temporal source/model/scope mismatch')
    expected = {f['frame_index']: (w, f) for w in request['windows'] for f in w['frames']}
    parent_frames = {f['frame_index']: f for f in parent['frames']}
    seen = set()
    for frame in result['frames']:
        index = frame['frame_index']
        if index not in expected or index in seen:
            raise ValueError('Temporal frame identity changed')
        seen.add(index)
        window, pinned = expected[index]
        if frame.get('window_id') != window['id'] or any(frame.get(k) != v for k, v in pinned.items()):
            raise ValueError('Temporal frame provenance changed')
        if any(frame[k] != parent_frames[index][k] for k in ['clip_pts', 'time_base', 'rgb_sha256', 'timestamp_ms']):
            raise ValueError('Temporal frame differs from source')
        prompts = {p['id']: p for p in window['prompts']}
        instances = frame['temporal_instances']
        if len(instances) != len(prompts) or {i['seed_object_id'] for i in instances} != prompts.keys():
            raise ValueError('Temporal seed identity changed')
        for instance in instances:
            mask = instance['mask']
            prompt = prompts[instance['seed_object_id']]
            if instance.get('proposal_group') != prompt.get('proposal_group'):
                raise ValueError('Temporal proposal group changed')
            group = prompt.get('proposal_group')
            if group:
                seed_objects = {o['id']: o for o in parent_frames[window['frames'][0]['frame_index']]['objects']}
                if group['physical_identity_confirmed'] is not False or group['representative_id'] != prompt['id']:
                    raise ValueError('Temporal group identity was promoted')
                for member in group['members']:
                    if member['id'] not in seed_objects or any(member[k] != seed_objects[member['id']][k] for k in ['label', 'confidence', 'box']):
                        raise ValueError('Group member differs from source detector')
            if (receipt['files'].get(mask['file']) != mask['sha256']
                    or instance['seed_frame_index'] != window['frames'][0]['frame_index']
                    or instance['label'] != prompts[instance['seed_object_id']]['label']):
                raise ValueError('Temporal mask/seed not bound to producer')
            with Image.open(directory / mask['file']) as image:
                pixels = np.asarray(image)
                if (image.format != 'PNG' or image.size != tuple(result['dimensions'])
                        or pixels.ndim != 2 or not np.isin(pixels, [0, 1]).all()
                        or int(pixels.sum()) != instance['visible_pixels']):
                    raise ValueError('Temporal native raster/count mismatch')
    if seen != expected.keys():
        raise ValueError('Temporal producer omitted frames')
    return result
