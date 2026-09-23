"""GPU physical-display inference using received weights and FR selection code."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import time

from labprism.artifacts import freeze_sources, sha256, verify_run
from labprism.contracts import validate_result
from labprism.runtime.observation import verify_observation


def load_recipe(path):
    recipe = json.loads(Path(path).read_text())
    model = recipe['model']
    if recipe.get('schema_version') != 'labprism-display-video-recipe/1':
        raise ValueError('Unsupported display recipe')
    if not 1 <= recipe['sample_hz'] <= 10:
        raise ValueError('Sampling must be bounded to 1–10 Hz')
    for item in (model, recipe['selection']):
        if sha256(item['path']) != item['sha256']:
            raise ValueError('Received model or selection implementation changed')
    receipt = json.loads(Path(model['receipt']).read_text())
    if (sha256(model['receipt']) != model['receipt_sha256']
            or receipt['weights_sha256'] != model['sha256']
            or receipt['project_id'] != 'instrument-display-surface-v2'
            or receipt['role'] != model['role'] or receipt['production_replacement'] is not False):
        raise ValueError('Candidate identity or deployment status differs')
    producer = Path(model['receipt']).parent / 'producer-receipt.json'
    if sha256(producer) != receipt['producer_receipt_sha256']:
        raise ValueError('Producer receipt changed')
    return recipe


def run(media, output, recipe_path):
    import av
    import numpy as np
    import torch
    from ultralytics import YOLO

    source = verify_observation(media)
    recipe = load_recipe(recipe_path)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA 不可用；没有回退到 CPU')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'evidence').mkdir()
    project = Path(__file__).resolve().parents[3]
    frozen = freeze_sources(project, sorted((project / 'src/labprism').rglob('*.py')), output / 'source.zip')
    shutil.copyfile(recipe['selection']['path'], output / 'display_selection.py')
    spec = importlib.util.spec_from_file_location('received_display_selection', output / 'display_selection.py')
    selector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selector)
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    model = YOLO(recipe['model']['path'])
    if model.names != {0: 'display_surface'}:
        raise ValueError('Physical-display ontology differs')
    frames = []
    next_ms = 0
    with av.open(str(Path(media) / 'clip.mp4')) as clip:
        stream = clip.streams.video[0]
        width, height = stream.width, stream.height
        origin = float((stream.start_time or 0) * stream.time_base * 1000)
        duration = float(stream.duration * stream.time_base * 1000) if stream.duration else source['duration_seconds'] * 1000
        for index, decoded in enumerate(clip.decode(stream)):
            if decoded.pts is None:
                raise ValueError('Missing native video PTS')
            timestamp = round(float(decoded.pts * decoded.time_base * 1000) - origin, 6)
            if timestamp < -0.001:
                continue
            if timestamp + .001 < next_ms:
                continue
            next_ms = (int((timestamp + .001) * recipe['sample_hz'] / 1000) + 1) * 1000 / recipe['sample_hz']
            rgb = decoded.to_ndarray(format='rgb24')
            torch.cuda.synchronize()
            tick = time.perf_counter()
            prediction = model.predict(rgb[:, :, ::-1].copy(), device=0, imgsz=960, rect=True,
                                       conf=.25, iou=.7, max_det=12, half=True, verbose=False)[0]
            torch.cuda.synchronize()
            elapsed = (time.perf_counter() - tick) * 1000
            raw = [{'xyxy': [float(v) for v in b.xyxy[0].tolist()], 'confidence': float(b.conf.item()),
                    'class_id': int(b.cls.item())} for b in prediction.boxes]
            selection = selector.select(raw)
            objects = [dict(id=f'f{index}-o{i}', class_id=0, label='display_surface', display_name='物理显示窗',
                            confidence=raw[i]['confidence'], box=raw[i]['xyxy'], mask_contours=[],
                            mask_score=None, track_id=None) for i in selection['selected_indices']]
            frames.append(dict(frame_index=index, timestamp_ms=timestamp, clip_pts=decoded.pts,
                               time_base=str(decoded.time_base), presentation_seconds=timestamp / 1000,
                               source_timestamp_ms=source['parent_start_seconds'] * 1000 + timestamp,
                               rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(), objects=objects, hands=[],
                               raw_display_proposals=raw, display_selection=selection,
                               availability={**{key: 'not_run' for key in ['hands', 'tracking', 'instance_segmentation', 'semantic_segmentation', 'ocr', 'events']},
                                             'detection': 'predicted' if objects else 'no_detection'},
                               latency_ms={'detector': round(elapsed, 3)}))
            if len(frames) == 1 or len(frames) % 10 == 0:
                print(json.dumps({'stage': 'running', 'frames': len(frames), 'timestamp_ms': timestamp,
                                  'duration_ms': duration, 'progress': min(.99, timestamp / duration)}), flush=True)
    wall = time.perf_counter() - started
    if not frames:
        raise ValueError('Video contains no decodable frames')
    shutil.copyfile(Path(media) / 'clip.mp4', output / 'clip.mp4')
    shutil.copyfile(Path(media) / 'receipt.json', output / 'producer-receipt.json')
    shutil.copyfile(recipe_path, output / 'recipe.json')
    shutil.copyfile(recipe['model']['receipt'], output / 'received-model-receipt.json')
    shutil.copyfile(Path(recipe['model']['receipt']).parent / 'producer-receipt.json', output / 'training-producer-receipt.json')
    registry = {'models': [recipe['model']]}
    (output / 'model-receipt.json').write_text(json.dumps(registry))
    statuses = {key: dict(state='not_run', reason='本次仅执行物理显示窗检测')
                for key in ['instance_masks', 'semantic_map', 'keypoints', 'tracks', 'relations', 'events', 'readouts']}
    statuses['boxes'] = dict(state='predicted' if any(f['objects'] for f in frames) else 'no_detection', reason='实际 CUDA 检测及固定 FR 几何去重；候选未晋级')
    result = dict(
        schema_version='labprism-video-result/4', created_at=datetime.now(timezone.utc).isoformat(),
        mode='offline_sampled_inference', prediction_status='unreviewed_model_proposals',
        data_use={'purpose': 'production_observation' if source['split'] is None else 'development'},
        source={**source, 'clip_sha256': sha256(output / 'clip.mp4')},
        video=dict(file='clip.mp4', width=width, height=height, duration_ms=duration, sample_hz=recipe['sample_hz'],
                   coordinate_system='clip_pixels_top_left_xy', mirror_applied=False, rotation_applied=False),
        ontology=dict(schema_version='labprism-ontology/1', display_names={'display_surface': '物理显示窗'}, display_language='zh-CN'),
        semantic_taxonomy=dict(id='not_run', version='1', classes=[], unknown_id=None, ignore_id=None),
        time_mapping=dict(clip_origin_ms=origin, capture_origin_ms=None, global_origin_ms=None),
        coordinates=dict(clip_to_source=[[source['source_dimensions'][0] / width, 0, 0],
                                        [0, source['source_dimensions'][1] / height, 0], [0, 0, 1]],
                         operations=[] if source['source_dimensions'] == [width, height] else
                         [{'type': 'producer_resize', 'source_dimensions': source['source_dimensions'], 'clip_dimensions': [width, height]}]),
        models=registry['models'], configuration={**recipe, 'detector_imgsz': 960, 'confidence': .25, 'iou': .7, 'max_det': 12,
                                               'role_transfer_diagnostic': source['camera_role'] != recipe['model']['role']},
        environment=dict(gpu=torch.cuda.get_device_name(), cuda=torch.version.cuda, torch=torch.__version__,
                         actual_execution_providers={'detector': 'CUDA:0 FP16'}, inference_batch=1),
        frames=frames, events=[], output_statuses=statuses,
        metrics=dict(accuracy=None, generalization=None, temporal_quality=None, npu_fps=None,
                     processed_frames=len(frames), decoded_inference_wall_seconds=wall,
                     sampled_pipeline_fps=len(frames) / wall,
                     peak_torch_allocated_mib=torch.cuda.max_memory_allocated() / 2**20,
                     module_warm_p50_ms={'detector': float(np.median([f['latency_ms']['detector'] for f in frames[1:] or frames]))}),
        limitations=['候选显示窗定位；未执行文字、手姿、分割、身份或实验步骤识别',
                     '原始逐帧检测与去重记录保留；稀疏采样之间不补造预测',
                     '相机角色由来源或用户声明；跨角色输出仅作诊断；无独立连续视频质量标注'])
    validate_result(result)
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    receipt = dict(schema_version='labprism-inference-run/1', files={p.name: sha256(p) for p in output.iterdir() if p.is_file()},
                   evidence={}, source_sha256=source['source_sha256'], model_receipt_sha256=sha256(output / 'model-receipt.json'),
                   source_files=frozen)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    verify_run(output)
    print(json.dumps({'stage': 'complete', 'metrics': result['metrics']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('media')
    parser.add_argument('output')
    parser.add_argument('--recipe', required=True)
    args = parser.parse_args()
    run(args.media, args.output, args.recipe)
