#!/usr/bin/env python3
"""Replay the configured VisionCortex detector on every pinned parent sample."""
import argparse
from datetime import datetime, timezone
import fcntl
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from labprism.artifacts import freeze_sources, sha256, verify_run
from labprism.contracts import validate_result
from run_upstream_video_masks import validate_destination


def check_decoded_sample(frame, rgb, decoder_ms, dimensions):
    if (list(rgb.shape[:2][::-1]) != dimensions
            or hashlib.sha256(rgb.tobytes()).hexdigest() != frame['rgb_sha256']
            or abs(decoder_ms - float(Fraction(frame['time_base']) * frame['clip_pts']) * 1000) > .1):
        raise ValueError('Decoder pixels, dimensions or position differ from pinned sample')


def run(args):
    import cv2
    import numpy as np
    import torch

    sys.path.insert(0, str(args.producer_repo / 'src'))
    from visioncortex import detection
    from visioncortex.config import load_config
    from visioncortex.detection_duplicates import duplicate_suppression_policies, suppress_duplicate_boxes
    from visioncortex.schemas import ViewInput, ViewRole

    validate_destination(args.output)
    parent = verify_run(args.parent)
    if parent['source']['split'] not in {'train', 'val'}:
        raise ValueError('Development source required')
    config = load_config(args.config)
    role = ViewRole(parent['source']['camera_role'])
    engine = detection._select_model_path(role, config)
    if engine.suffix != '.engine' or sha256(engine) != args.engine_sha256:
        raise ValueError('Configured engine differs from pinned deployment')
    lock = args.gpu_lock.open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError('Insufficient shared CUDA memory')
    torch.set_num_threads(4)
    cv2.setNumThreads(2)
    args.output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    snapshot = Path(json.loads((repo / 'configs/project.json').read_text())['data_root_default']) / 'source-snapshots'
    pin = sha256(args.parent / 'result.json')[:16] + '-' + args.engine_sha256[:12]
    implementation = {
        'consumer': freeze_sources(repo, [Path(__file__), repo / 'scripts/run_upstream_video_masks.py',
            *sorted((repo / 'src/labprism').rglob('*.py'))], snapshot / ('detector-consumer-' + pin + '.zip')),
        'producer': freeze_sources(args.producer_repo, sorted((args.producer_repo / 'src/visioncortex').rglob('*.py')),
                                  snapshot / ('detector-producer-' + pin + '.zip'))}
    width, height = parent['video']['width'], parent['video']['height']
    display = json.loads((repo / 'configs/models/class-display-names.json').read_text())
    model = {'id': 'visioncortex-service-' + role.value + '-' + args.engine_sha256[:12],
        'task': 'object_detection', 'role': role.value, 'path': str(engine),
        'sha256': args.engine_sha256, 'backend': 'TensorRT CUDA FP16',
        'status': 'current_service_model_replay', 'code_revision': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=args.producer_repo, text=True).strip()}
    result = {'schema_version': 'labprism-video-result/3', 'created_at': datetime.now(timezone.utc).isoformat(),
        'source': parent['source'], 'video': parent['video'], 'models': [model], 'frames': [], 'events': [],
        'ontology': {'schema_version': 'labprism-ontology/1', 'display_names': display, 'display_language': 'zh-CN'},
        'mode': 'offline_sampled_inference', 'prediction_status': 'unreviewed_model_proposals',
        'configuration': {}, 'derived_from': {'result_sha256': sha256(args.parent / 'result.json'),
        'receipt_sha256': sha256(args.parent / 'receipt.json')},
        'limitations': ['Current production detector on existing exposed development video; not independent accuracy',
            'Only detections recomputed here; old masks, hand pose, tracks, relations and actions are not relabelled as new',
            'Parent PTS/timebase retained after exact clip, ordinal, RGB and decoder-time verification']}
    targets = {f['frame_index']: f for f in parent['frames']}
    view = ViewInput(view_id=parent['source']['camera_id'], role=role, video=args.parent / 'clip.mp4')
    scanner = detection.RoleScanner(role, config, appearance_enabled=False)
    policy = duplicate_suppression_policies(config).get(role)
    started = time.perf_counter()
    pending = []
    original = []
    batch_times = []
    removed = 0
    inference_batches = []

    def flush():
        nonlocal removed
        if not pending:
            return
        torch.cuda.synchronize()
        start = time.perf_counter()
        predictions = scanner.infer(pending)
        torch.cuda.synchronize()
        batch_times.append(time.perf_counter() - start)
        inference_batches.extend(scanner.last_engine_batch_sizes)
        for frame, boxes in zip(original, predictions, strict=True):
            audit = None
            if policy:
                boxes, audit = suppress_duplicate_boxes(boxes, policy['iou_threshold'])
                removed += len(audit.removals)
            objects = [{'id': f'f{frame["frame_index"]}-service-o{i}', 'class_id': b.class_id,
                'label': b.class_name, 'display_name': display.get(b.class_name, b.class_name),
                'confidence': b.confidence, 'box': [v * (width if j % 2 == 0 else height)
                                                  for j, v in enumerate(b.xyxy_norm)],
                'model_id': model['id'], 'mask_contours': []} for i, b in enumerate(boxes)]
            row = {k: frame[k] for k in ['frame_index', 'timestamp_ms', 'presentation_seconds', 'clip_pts',
                'time_base', 'source_timestamp_ms', 'rgb_sha256']}
            row.update(objects=objects, hands=[], availability={'detection': 'predicted',
                **{k: 'not_run' for k in ['instance_segmentation', 'hands', 'tracking', 'ocr', 'events']}},
                detection_duplicate_audit=audit.model_dump(mode='json') if audit else None)
            result['frames'].append(row)
        pending.clear()
        original.clear()

    capture = cv2.VideoCapture(str(args.parent / 'clip.mp4'))
    try:
        index = 0
        while capture.grab():
            if index in targets:
                ok, bgr = capture.retrieve()
                if not ok:
                    raise RuntimeError('Source decode failed')
                frame = targets[index]
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                check_decoded_sample(frame, rgb, capture.get(cv2.CAP_PROP_POS_MSEC), [width, height])
                pending.append(detection.FramePacket(view, index, frame['timestamp_ms'], bgr,
                    cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), None, 0.0))
                original.append(frame)
                if len(pending) == scanner.batch_size:
                    flush()
            index += 1
        flush()
        if {f['frame_index'] for f in result['frames']} != targets.keys():
            raise ValueError('Incomplete sampled video')
        backend = scanner.model.predictor.model
        if backend.format != 'engine' or backend.device.type != 'cuda':
            raise RuntimeError('Actual backend was not TensorRT CUDA')
        result['configuration'] = {'imgsz': scanner.image_size, 'confidence': config['models']['confidence'],
            'iou': config['models']['iou'], 'max_detections': config['models']['max_detections'],
            'final_duplicate_policy': policy, 'actual_engine_batches': sorted(set(inference_batches)),
            'end2end': bool(backend.end2end), 'exact_batch_padding_frames': scanner.exact_batch_padding_frames}
        result['environment'] = {'gpu': torch.cuda.get_device_name(0), 'torch': torch.__version__,
            'actual_execution_providers': {'detector': 'TensorRT CUDA FP16'}}
        result['metrics'] = {'processed_frames': len(result['frames']),
            'observations': sum(len(f['objects']) for f in result['frames']), 'stage_seconds': time.perf_counter() - started,
            'inference_batch_seconds': sum(batch_times), 'inference_batches': len(batch_times),
            'suppressed_duplicates': removed, 'nms_timeout_retries': scanner.nms_timeout_retries,
            'scope': 'decode + model load/inference + proposal mapping; excludes other modules and artifact publication',
            'accuracy': None, 'generalization': None, 'temporal_quality': None, 'full_pipeline_fps': None, 'npu_fps': None}
    finally:
        capture.release()
        scanner.close()
        fcntl.flock(lock, fcntl.LOCK_UN)
    validate_result(result)
    for source, name in [(args.parent / 'clip.mp4', 'clip.mp4'),
                         (args.parent / 'producer-receipt.json', 'producer-receipt.json'),
                         (args.parent / 'result.json', 'baseline-result.json'),
                         (args.parent / 'receipt.json', 'baseline-receipt.json')]:
        shutil.copyfile(source, args.output / name)
    (args.output / 'model-receipt.json').write_text(json.dumps({'schema_version': 'labprism-model-receipt/1', 'models': [model]}))
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    receipt = {'schema_version': 'labprism-inference-run/1',
        'files': {p.name: sha256(p) for p in args.output.iterdir() if p.is_file()}, 'evidence': {},
        'model_receipt_sha256': sha256(args.output / 'model-receipt.json'),
        'source_sha256': result['source']['source_sha256'], 'implementation': implementation,
        'production_service_changed': False}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    verify_run(args.output)
    print(json.dumps(result['metrics']), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['parent', 'output', 'producer-repo', 'config', 'gpu-lock']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--engine-sha256', required=True)
    run(p.parse_args())
