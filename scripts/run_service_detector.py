#!/usr/bin/env python3
"""Run the configured VisionCortex detector on receipted video or pinned samples."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from labprism.artifacts import freeze_sources, sha256, verify_run
from labprism.contracts import validate_result
from labprism.runtime.detector_input import detector_input
from run_upstream_video_masks import validate_destination


def run(args):
    validate_destination(args.output)
    with ExitStack() as resources:
        parent, samples = resources.enter_context(detector_input(
            parent=args.parent, media=args.media, sample_hz=args.sample_hz))
        lock = resources.enter_context(args.gpu_lock.open('a'))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return infer(args, parent, samples, resources)


def infer(args, parent, samples, resources):
    import cv2
    import torch

    sys.path.insert(0, str(args.producer_repo / 'src'))
    from visioncortex import detection
    from visioncortex.config import load_config
    from visioncortex.detection_duplicates import duplicate_suppression_policies, suppress_duplicate_boxes
    from visioncortex.schemas import ViewInput, ViewRole

    input_dir = args.parent if args.parent is not None else args.media
    config = load_config(args.config)
    role = ViewRole(parent['source']['camera_role'])
    engine = detection._select_model_path(role, config)
    if engine.suffix != '.engine' or sha256(engine) != args.engine_sha256:
        raise ValueError('Configured engine differs from pinned deployment')
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError('Insufficient shared CUDA memory')
    torch.set_num_threads(4)
    cv2.setNumThreads(2)
    args.output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    snapshot = Path(json.loads((repo / 'configs/project.json').read_text())['data_root_default']) / 'source-snapshots'
    snapshot.mkdir(parents=True, exist_ok=True)
    pin = sha256(input_dir / 'receipt.json')[:16] + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
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
        'status': 'candidate_model_replay' if args.candidate else 'current_service_model_replay',
        'code_revision': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=args.producer_repo, text=True).strip()}
    result = {'schema_version': parent.get('schema_version', 'labprism-video-result/3'), 'created_at': datetime.now(timezone.utc).isoformat(),
        'source': parent['source'], 'video': parent['video'], 'models': [model], 'frames': [], 'events': [],
        'ontology': {'schema_version': 'labprism-ontology/1', 'display_names': display, 'display_language': 'zh-CN'},
        'mode': 'offline_sampled_inference', 'prediction_status': 'unreviewed_model_proposals',
        'configuration': {},
        'limitations': ['Configured detector inference; no independent accuracy measurement or implicit training authorization',
            'Only detections recomputed here; old masks, hand pose, tracks, relations and actions are not relabelled as new',
            'Native PTS/timebase and pixel hashes retained; sparse samples do not imply predictions on intervening frames']}
    if args.parent is not None:
        result['derived_from'] = {'result_sha256': sha256(args.parent / 'result.json'),
                                  'receipt_sha256': sha256(args.parent / 'receipt.json')}
    if result['schema_version'] == 'labprism-video-result/4':
        for key in ('data_use', 'semantic_taxonomy', 'time_mapping', 'coordinates'):
            result[key] = parent[key]
        result['output_statuses'] = {key: {'state': 'not_run', 'reason': 'Only detector inference requested'}
            for key in ('boxes', 'instance_masks', 'semantic_map', 'keypoints', 'tracks', 'relations', 'events', 'readouts')}
        result['semantic_taxonomy'] = {'id': 'not_run', 'version': '1', 'classes': [], 'unknown_id': None, 'ignore_id': None}
    view = ViewInput(view_id=parent['source']['camera_id'], role=role, video=input_dir / 'clip.mp4')
    scanner = detection.RoleScanner(role, config, appearance_enabled=False)
    resources.callback(scanner.close)
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
            row.update(objects=objects, hands=[], availability={'detection': 'predicted' if objects else 'no_detection',
                **{k: 'not_run' for k in ['instance_segmentation', 'semantic_segmentation', 'hands', 'tracking', 'ocr', 'events']}},
                detection_duplicate_audit=audit.model_dump(mode='json') if audit else None)
            result['frames'].append(row)
        pending.clear()
        original.clear()

    for frame, bgr in samples:
        pending.append(detection.FramePacket(view, frame['frame_index'], frame['timestamp_ms'], bgr,
            cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), None, 0.0))
        original.append(frame)
        if len(pending) == scanner.batch_size:
            flush()
            if len(result['frames']) % 100 == 0:
                print(json.dumps({'processed_frames': len(result['frames']), 'timestamp_ms': frame['timestamp_ms']}), flush=True)
    flush()
    backend = scanner.model.predictor.model
    if backend.format != 'engine' or backend.device.type != 'cuda':
        raise RuntimeError('Actual backend was not TensorRT CUDA')
    result['configuration'] = {'imgsz': scanner.image_size, 'confidence': scanner.prediction_confidence,
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
    if result['schema_version'] == 'labprism-video-result/4':
        result['output_statuses']['boxes'] = {'state': 'predicted' if any(f['objects'] for f in result['frames']) else 'no_detection',
            'reason': 'Actual configured TensorRT detector and shared duplicate suppression'}
    validate_result(result)
    if args.parent is not None:
        members = [(args.parent / 'clip.mp4', 'clip.mp4'),
                         (args.parent / 'producer-receipt.json', 'producer-receipt.json'),
                         (args.parent / 'result.json', 'baseline-result.json'),
                         (args.parent / 'receipt.json', 'baseline-receipt.json')]
    else:
        members = [(args.media / name, name) for name in parent['source']['files']]
        members.append((args.media / 'receipt.json', 'producer-receipt.json'))
    for source, name in members:
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
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--parent', type=Path, help='Replay exact samples from a receipted inference run')
    inputs.add_argument('--media', type=Path, help='Analyze a fresh receipted video without prior model output')
    p.add_argument('--sample-hz', type=float, default=5, help='Fresh-video sampling, 1–10 Hz; replay retains its original samples')
    for name in ['output', 'producer-repo', 'config', 'gpu-lock']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--engine-sha256', required=True)
    p.add_argument('--candidate', action='store_true', help='Record a candidate replay; does not claim a production deployment')
    run(p.parse_args())
