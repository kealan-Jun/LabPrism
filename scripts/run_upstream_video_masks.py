#!/usr/bin/env python3
"""Run VisionCortex's receipted SAM2 producer and consume its temporal masks."""
import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from labprism.artifacts import sha256, verify_run
from labprism.perception.trained_hand import verify_decoded_frame
from labprism.tracking.upstream_video_masks import validate_handoff


def validate_destination(output):
    repo = Path(__file__).resolve().parents[1]
    config = json.loads((repo / 'configs/project.json').read_text())
    nas = Path(os.environ.get('LABPRISM_NAS_ROOT', config['nas_root_default'])).resolve()
    output.resolve().relative_to(nas)
    if json.loads((nas / '.labprism-volume.json').read_text())['volume_id'] != config['nas_volume_id']:
        raise ValueError('NAS identity unavailable')
    if 'cifs' not in subprocess.check_output(['findmnt', '-T', str(nas), '-n', '-o', 'FSTYPE'], text=True):
        raise ValueError('NAS is not mounted')


def run(args):
    import av
    import numpy as np
    from PIL import Image

    validate_destination(args.output)
    parent = verify_run(args.parent)
    if parent['source']['split'] not in {'train', 'val'}:
        raise ValueError('Development input required')
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = args.output / 'input'
    inputs.mkdir()
    request = {'schema_version': 'visioncortex-temporal-mask-request/1',
        'source': parent['source'], 'parent_result_sha256': sha256(args.parent / 'result.json'),
        'dimensions': [parent['video']['width'], parent['video']['height']],
        'input_transform': {'encoding': 'JPEG', 'quality': 95, 'resize': False}, 'windows': []}
    targets = {}
    for offset in range(0, len(parent['frames']), 50):
        subset = parent['frames'][offset:offset + 50]
        prompts = sorted((o for o in subset[0]['objects'] if o['label'] not in {'hand', 'gloved_hand'}),
                         key=lambda o: -o['confidence'])[:3]
        if not prompts:
            continue
        window_id = len(request['windows'])
        window = {'id': window_id, 'prompts': [{k: p[k] for k in ['id', 'label', 'box', 'display_name'] if k in p}
                                             for p in prompts], 'frames': []}
        (inputs / 'frames' / f'{window_id:04d}').mkdir(parents=True)
        for position, frame in enumerate(subset):
            row = {k: frame[k] for k in ['frame_index', 'timestamp_ms', 'clip_pts', 'time_base', 'rgb_sha256']}
            row['input_file'] = f'frames/{window_id:04d}/{position:05d}.jpg'
            window['frames'].append(row)
            targets[frame['frame_index']] = (frame, row)
        request['windows'].append(window)
    seen = set()
    with av.open(str(args.parent / 'clip.mp4')) as container:
        for index, decoded in enumerate(container.decode(video=0)):
            if index not in targets:
                continue
            frame, row = targets[index]
            rgb = decoded.to_ndarray(format='rgb24')
            verify_decoded_frame(frame, rgb, decoded.pts, decoded.time_base, request['dimensions'])
            path = inputs / row['input_file']
            Image.fromarray(rgb).save(path, format='JPEG', quality=95)
            row['input_sha256'] = sha256(path)
            with Image.open(path) as image:
                row['input_rgb_sha256'] = hashlib.sha256(np.asarray(image.convert('RGB')).tobytes()).hexdigest()
            seen.add(index)
    if seen != targets.keys():
        raise ValueError('Incomplete exact source decode')
    request_path = inputs / 'request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2))
    print(json.dumps({'prepared_frames': len(seen), 'windows': len(request['windows'])}), flush=True)
    lock = args.gpu_lock.open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = dict(os.environ, PYTHONPATH=str(args.producer_repo / 'src'), OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
    subprocess.run([str(args.python), '-c',
        'import torch; assert torch.cuda.is_available(); assert torch.cuda.mem_get_info()[0] > 7*1024**3'],
        env=env, check=True)
    producer = args.output / 'producer'
    with (args.output / 'producer.log').open('w') as log:
        subprocess.run([str(args.python), '-m', 'visioncortex.temporal_mask_handoff',
            '--request', str(request_path), '--config', str(args.config), '--output', str(producer)],
            env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    fcntl.flock(lock, fcntl.LOCK_UN)
    receive(args, request_path, producer, parent)


def receive(args, request_path, producer, parent):
    validate_destination(args.output)
    request = json.loads(request_path.read_text())
    if request['parent_result_sha256'] != sha256(args.parent / 'result.json'):
        raise ValueError('Frozen parent changed before receive')
    handoff = validate_handoff(producer, request_path, parent)
    result = copy.deepcopy(parent)
    result['created_at'] = datetime.now(timezone.utc).isoformat()
    result['derived_from'] = {'result_sha256': request['parent_result_sha256'],
                              'receipt_sha256': sha256(args.parent / 'receipt.json')}
    result['parent_metrics'] = result['metrics']
    result['configuration'].update(temporal_mask_propagation=True, temporal_window_frames=50,
        temporal_max_objects=3, temporal_input_transform=request['input_transform'],
        temporal_producer_receipt_sha256=sha256(producer / 'receipt.json'))
    predictions = {f['frame_index']: f for f in handoff['frames']}
    for frame in result['frames']:
        frame['temporal_instances'] = predictions.get(frame['frame_index'], {}).get('temporal_instances', [])
        frame['availability']['video_segmentation'] = 'sam2_memory_candidate' if frame['temporal_instances'] else 'not_prompted'
    result['temporal_windows'] = [{'id': f'window-{w["id"]}',
        'first_frame_index': w['frames'][0]['frame_index'], 'last_frame_index': w['frames'][-1]['frame_index'],
        'source_frame_indices': [f['frame_index'] for f in w['frames']],
        'prompt_ids': [p['id'] for p in w['prompts']], 'identity_across_windows': False}
        for w in request['windows']]
    runtime = handoff['model']
    expected = json.loads(args.config.read_text())['models']['temporal_participant_segmentation']
    if runtime['checkpoint_sha256'] != expected['checkpoint_sha256']:
        raise ValueError('Producer used a different checkpoint')
    model = {'id': 'visioncortex-sam2-' + runtime['checkpoint_sha256'][:12],
        'task': 'video_instance_segmentation', 'sha256': runtime['checkpoint_sha256'],
        'path': runtime['checkpoint'], 'backend': 'official SAM2VideoPredictor CUDA BF16',
        'source_revision': runtime['source_revision'], 'status': 'unreviewed_model_proposals'}
    result['models'].append(model)
    result['metrics'] = {**handoff['metrics'], 'processed_frames': len(parent['frames']),
        'temporal_frames': len(handoff['frames']), 'temporal_windows': len(request['windows']),
        'observations': sum(len(f['temporal_instances']) for f in handoff['frames']),
        'scope': 'SAM2 temporal stage including model load, input JPEG decode and mask serialization; excludes source export and other modules',
        'generalization': None, 'full_pipeline_fps': None, 'npu_fps': None}
    result.setdefault('limitations', []).extend([
        'Temporal masks are unreviewed proposals; identity resets every 50 sampled frames',
        'Official SAM2 input is a declared JPEG95 derivative; original PTS/RGB and derived file/RGB hashes retained',
        'No cross-camera identity, calibrated physical contact or action confirmation inferred',
        'Existing development footage has training exposure; no independent generalization claim'])
    output = args.output / ('consumer-final' if args.receive_only else 'consumer')
    output.mkdir()
    # Preserve every parent-bound raster/evidence artifact referenced by unchanged layers.
    parent_receipt = json.loads((args.parent / 'receipt.json').read_text())
    for name in parent_receipt['files']:
        if name not in {'result.json', 'receipt.json', 'model-receipt.json', 'baseline-result.json', 'baseline-receipt.json'}:
            shutil.copyfile(args.parent / name, output / name)
    if (args.parent / 'evidence').is_dir():
        shutil.copytree(args.parent / 'evidence', output / 'evidence')
    for name in ['result.json', 'receipt.json']:
        shutil.copyfile(args.parent / name, output / ('baseline-' + name))
        shutil.copyfile(producer / name, output / ('temporal-producer-' + name))
    shutil.copyfile(request_path, output / 'temporal-request.json')
    for frame in handoff['frames']:
        for instance in frame['temporal_instances']:
            name = instance['mask']['file']
            shutil.copyfile(producer / name, output / name)
    (output / 'model-receipt.json').write_text(json.dumps({'schema_version': 'labprism-model-receipt/1', 'models': result['models']}))
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    receipt = {'schema_version': 'labprism-inference-run/1',
        'files': {p.name: sha256(p) for p in output.iterdir() if p.is_file()},
        'evidence': {p.name: sha256(p) for p in (output / 'evidence').iterdir()} if (output / 'evidence').is_dir() else {},
        'source_sha256': result['source']['source_sha256'], 'model_receipt_sha256': sha256(output / 'model-receipt.json'),
        'implementation_sha256': sha256(__file__),
        'validator_sha256': sha256(Path(__file__).resolve().parents[1] / 'src/labprism/tracking/upstream_video_masks.py'),
        'promotion': 'none'}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    verify_run(output)
    print(json.dumps(result['metrics']), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['parent', 'output', 'producer-repo', 'python', 'config', 'gpu-lock']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--receive-only', action='store_true')
    args = p.parse_args()
    if args.receive_only:
        receive(args, args.output / 'input/request.json', args.output / 'producer', verify_run(args.parent))
    else:
        run(args)
