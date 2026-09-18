"""Add measured 2D hands, image-supported tracking, OCR and proximity evidence."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import time

from labprism.artifacts import sha256, verify_run
from labprism.contracts import validate_result
from labprism.perception.baseline import source_revision
from labprism.tracking.association import Tracker, deduplicate_hands
from labprism.tracking.appearance import AppearanceTracker, CameraMotion
from labprism.understanding.proximity import relations_for_frame, build_events


def run(baseline, output, model_receipt, ocr_interval_ms=1000):
    import av
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    from rtmlib import RTMPose

    if ocr_interval_ms <= 0:
        raise ValueError('OCR interval must be positive')
    baseline, output, model_receipt = Path(baseline), Path(output), Path(model_receipt)
    parent = verify_run(baseline)
    registry = json.loads(model_receipt.read_text())
    models = {m['task']:m for m in registry['models']}
    selected = [models[k] for k in ['hand_landmarks_candidate','ocr_detection','ocr_orientation','ocr_recognition']]
    for model in selected:
        if sha256(model['path']) != model['sha256']:
            raise ValueError('Model identity mismatch: '+model['id'])
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cv2.setNumThreads(2)
    pose = RTMPose(onnx_model=models['hand_landmarks_candidate']['path'], model_input_size=(256,256),
                  backend='onnxruntime', device='cpu')
    ocr = RapidOCR(det_model_path=models['ocr_detection']['path'],
                   cls_model_path=models['ocr_orientation']['path'],
                   rec_model_path=models['ocr_recognition']['path'],
                   intra_op_num_threads=2, inter_op_num_threads=1,
                   det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False)
    providers = {
        'text_det': ocr.text_det.infer.session.get_providers(),
        'text_cls': ocr.text_cls.infer.session.get_providers(),
        'text_rec': ocr.text_rec.session.session.get_providers(),
    }
    if any(v[0] != 'CPUExecutionProvider' for v in providers.values()):
        raise ValueError('Unexpected OCR execution provider')
    result = copy.deepcopy(parent)
    result['schema_version'] = 'labprism-video-result/3'
    result['created_at'] = datetime.now(timezone.utc).isoformat()
    result['derived_from'] = {'result_sha256':sha256(baseline/'result.json'),
                              'receipt_sha256':sha256(baseline/'receipt.json')}
    result['models'] = parent['models'] + [m for m in selected if m not in parent['models']]
    result['environment']['packages'].update({k:importlib.metadata.version(k) for k in ['rapidocr-onnxruntime','rtmlib','onnxruntime','opencv-python']})
    result['environment']['ocr_providers'] = providers
    result['environment']['hand_candidate_provider'] = 'ONNXRuntime CPUExecutionProvider'
    result['configuration'].update(ocr_interval_ms=ocr_interval_ms, ocr_min_score=.5,
        tracking='causal_affine_appearance_hungarian', tracking_max_gap_ms=2000,
        proximity_threshold_px=15, event_min_observations=4, event_min_duration_ms=600,
        sample_validity_ms=min(150,1000/parent['video']['sample_hz']))
    interval = 1000/parent['video']['sample_hz']
    tracker = AppearanceTracker(sample_interval_ms=interval)
    comparison = Tracker()
    hand_tracker = AppearanceTracker('hand',sample_interval_ms=interval)
    motion = CameraMotion()
    next_ocr, count = 0, 0
    processing_started = time.perf_counter()
    targets = {f['frame_index']:f for f in result['frames']}
    with av.open(str(baseline/'clip.mp4')) as container:
        for index, decoded in enumerate(container.decode(video=0)):
            if index not in targets:
                continue
            frame = targets[index]
            rgb = decoded.to_ndarray(format='rgb24')
            if hashlib.sha256(rgb.tobytes()).hexdigest() != frame['rgb_sha256']:
                raise ValueError('Frame pixels differ from baseline')
            bgr = cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
            t = time.perf_counter()
            boxes = deduplicate_hands(frame['objects'])
            points, scores = pose(bgr,bboxes=[o['box'] for o in boxes]) if boxes else ([],[])
            hands, rejected = [], []
            for i,(xy,score,obj) in enumerate(zip(points,scores,boxes)):
                if not np.isfinite(xy).all() or not np.isfinite(score).all():
                    continue
                h = {'id':f'f{index}-rh{i}','points':[[round(float(x),2),round(float(y),2),None] for x,y in xy],
                     'point_scores':[round(float(s),6) for s in score],'keypoint_threshold':.3,
                     'depth_available':False,'handedness_model_output':None,'handedness_score':None,
                     'box':obj['box'],'source_object_id':obj['id'],'model_id':selected[0]['id'],
                     'median_point_score':round(float(np.median(score)),6)}
                if np.median(score)>=.3 and (score>=.3).sum()>=8:
                    hands.append(h)
                else:
                    rejected.append(dict(h,reason='insufficient_keypoint_scores'))
            frame['baseline_hands'], frame['hands'], frame['rejected_hands'] = frame['hands'],hands,rejected
            latency = {'hand_candidate':(time.perf_counter()-t)*1000}
            t = time.perf_counter()
            affine, frame['camera_motion'] = motion.update(bgr,frame['objects'])
            comparison.update(copy.deepcopy(frame['objects']),frame['timestamp_ms'])
            tracker.update(frame['objects'],frame['timestamp_ms'],bgr,affine)
            tracked_hands = [dict(label='hand_keypoints',box=h['box']) for h in hands]
            hand_tracker.update(tracked_hands,frame['timestamp_ms'],bgr,affine)
            for hand,tracked in zip(hands,tracked_hands):
                for key in ['track_id','track_state','track_gap_ms','trail']:
                    hand[key] = tracked[key]
            latency['tracking'] = (time.perf_counter()-t)*1000
            frame['texts'] = []
            if frame['timestamp_ms'] >= next_ocr:
                next_ocr = frame['timestamp_ms'] + ocr_interval_ms
                t = time.perf_counter()
                readings, _ = ocr(bgr)
                for i,(quad,text,score) in enumerate(readings or []):
                    if score < .5:
                        continue
                    quad = np.asarray(quad,dtype=float)
                    quad[:,0] = np.clip(quad[:,0],0,result['video']['width']-1)
                    quad[:,1] = np.clip(quad[:,1],0,result['video']['height']-1)
                    frame['texts'].append({'id':f'f{index}-text{i}','quad':quad.round(2).tolist(),
                        'text':text,'score':round(float(score),6),'status':'unreviewed_model_proposal',
                        'model_id':models['ocr_recognition']['id'],'numeric_value':None,'unit':None})
                latency['ocr'] = (time.perf_counter()-t)*1000
                frame['availability']['ocr'] = 'predicted' if frame['texts'] else 'no_detection'
            else:
                frame['availability']['ocr'] = 'not_sampled'
            frame['relations'] = relations_for_frame(frame)
            frame['availability'].update(tracking='appearance_association_candidate',
                hands='predicted' if hands else 'no_detection',events='geometric_proximity_only',
                actions='not_run',steps='not_run')
            frame['candidate_latency_ms'] = {k:round(v,3) for k,v in latency.items()}
            count += 1
            if count % 50 == 0:
                print(json.dumps({'frames':count,'time_ms':frame['timestamp_ms'],'texts':len(frame['texts'])}),flush=True)
    if count != len(targets):
        raise ValueError('Missing source frames')
    result['events'] = build_events(result['frames'],max_gap_ms=interval*1.6)
    elapsed = time.perf_counter()-processing_started
    result['baseline_metrics'] = parent['metrics']
    result['metrics'] = {'accuracy':None,'generalization':None,'temporal_quality':None,'npu_fps':None,
        'sampled_pipeline_fps':None,'full_pipeline_latency_ms':None,
        'candidate_processing_fps':round(count/elapsed,3),'candidate_wall_seconds':round(elapsed,3),
        'candidate_total_wall_seconds':round(time.perf_counter()-started,3),
        'frames_with_hands':sum(bool(f['hands']) for f in result['frames']),
        'baseline_frames_with_hands':parent['metrics']['frames_with_hands'],
        'object_tracks_created':tracker.next_id,'iou_baseline_tracks_created':comparison.next_id,
        'hand_tracks_created':hand_tracker.next_id,'ocr_sampled_frames':sum(f['availability']['ocr']!='not_sampled' for f in result['frames']),
        'ocr_text_proposals':sum(len(f['texts']) for f in result['frames']),
        'proximity_events':len(result['events']), 'tracking_idf1':None,'ocr_accuracy':None,'event_accuracy':None}
    result['limitations'] = ['Parent detection and per-frame SAM masks reused; timing excludes parent computation',
        '2D hand scores are not calibrated visibility or keypoint accuracy; handedness and depth unknown',
        'Appearance/camera compensation association is unvalidated; fewer track IDs can also mean incorrect merges',
        'OCR is sampled once per second; intervening frames have no OCR observation; text is unreviewed',
        'Hand/object proximity uses visible predicted fingertips and detector boxes in image pixels, not physical contact',
        'Proximity intervals are not experiment actions, step recognition or calibrated global geometry',
        'Complete supplied files may themselves be curated excerpts; experiment completeness unverified',
        'No independent quality acceptance, training promotion, metric 3D or NPU measurements']
    validate_result(result)
    for name in ['clip.mp4','producer-receipt.json']:
        shutil.copyfile(baseline/name,output/name)
    for name in ['result.json','receipt.json']:
        shutil.copyfile(baseline/name,output/f'baseline-{name}')
    shutil.copyfile(model_receipt,output/'model-receipt.json')
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    manifest = {'schema_version':'labprism-inference-run/1',
        'files':{p.name:sha256(p) for p in output.iterdir() if p.is_file()},'evidence':{},
        'source_sha256':result['source']['source_sha256'],'model_receipt_sha256':sha256(model_receipt),
        **source_revision(Path(__file__).resolve().parents[3]),'implementation_sha256':sha256(__file__)}
    manifest['stage_implementation_sha256'] = {str(p.relative_to(Path(__file__).resolve().parents[1])):sha256(p)
        for p in [Path(__file__).resolve().parents[1]/'tracking/appearance.py',
                  Path(__file__).resolve().parents[1]/'understanding/proximity.py']}
    (output/'receipt.json').write_text(json.dumps(manifest,indent=2)+'\n')
    verify_run(output)
    print(json.dumps(result['metrics']),flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline');parser.add_argument('output');parser.add_argument('--models',required=True)
    args = parser.parse_args()
    run(args.baseline,args.output,args.models)
