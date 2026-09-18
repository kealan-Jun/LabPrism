"""Reproducible offline inference. Prediction proposals never become labels here."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

from labprism.artifacts import sha256, verify_media
from labprism.contracts import validate_result


def source_revision(project):
    """An extracted source archive has no Git checkout; never borrow cwd's HEAD."""
    project = Path(project)
    if not (project/'.git').exists():
        return {'git_commit':None, 'git_dirty':None}
    head = subprocess.run(['git','rev-parse','HEAD'],cwd=project,text=True,capture_output=True)
    if head.returncode:
        return {'git_commit':None, 'git_dirty':None}
    dirty = subprocess.check_output(['git','status','--porcelain'],cwd=project,text=True)
    return {'git_commit':head.stdout.strip(), 'git_dirty':bool(dirty.strip())}


def run(media, output, model_receipt, sample_hz=10):
    import av
    import cv2
    import mediapipe as mp
    import numpy as np
    import torch
    from ultralytics import YOLO, SAM

    media, output = Path(media), Path(output)
    source = verify_media(media)
    registry = json.loads(Path(model_receipt).read_text())
    detector_info = next(m for m in registry['models'] if m['task'] == 'object_detection' and m['role'] == source['camera_role'])
    mask_info = next(m for m in registry['models'] if m['task'] == 'box_prompted_instance_segmentation')
    hand_info = next(m for m in registry['models'] if m['task'] == 'hand_landmarks')
    for m in [detector_info, mask_info, hand_info]:
        if sha256(m['path']) != m['sha256']:
            raise ValueError('Model identity mismatch: ' + m['id'])
    if not torch.cuda.is_available():
        raise RuntimeError('This recipe requires CUDA; refusing an unreported CPU fallback')
    if not 0 < sample_hz <= 30:
        raise ValueError('sample_hz must be within (0,30]')
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / 'evidence'; evidence.mkdir()
    display_names = json.loads((Path(__file__).resolve().parents[3] / 'configs/models/class-display-names.json').read_text())
    started = time.perf_counter()
    torch.manual_seed(20260917)
    detector = YOLO(detector_info['path'])
    segmenter = SAM(mask_info['path'])
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=hand_info['path'], delegate=mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=0.5, min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5)
    hand_model = mp.tasks.vision.HandLandmarker.create_from_options(options)
    torch.cuda.reset_peak_memory_stats()
    frames, next_time = [], 0.0
    clip = av.open(str(media / 'clip.mp4'))
    stream = clip.streams.video[0]
    width, height = stream.width, stream.height
    # PyAV stream metadata belongs to the open container. Cache it before close;
    # accessing stream.duration afterwards can return invalid native memory.
    duration_ms = round(((stream.start_time or 0) + stream.duration)*float(stream.time_base)*1000, 6)
    decode_started = time.perf_counter()
    try:
        for frame_index, frame in enumerate(clip.decode(stream)):
            pts = float(frame.pts * frame.time_base)
            timestamp_ms = round(pts * 1000, 6)
            if timestamp_ms + 0.001 < next_time: continue
            next_time += 1000 / sample_hz
            rgb = frame.to_ndarray(format='rgb24')
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            torch.cuda.synchronize(); t = time.perf_counter()
            detection = detector.predict(bgr, device=0, imgsz=960, conf=0.25, iou=0.7, max_det=100, half=True, verbose=False)[0]
            torch.cuda.synchronize(); det_ms = (time.perf_counter()-t)*1000
            boxes = detection.boxes.xyxy.cpu().numpy()
            objects = [dict(id=f'f{frame_index}-o{i}', class_id=int(box.cls.item()), label=detection.names[int(box.cls.item())], confidence=round(float(box.conf.item()),5), box=[round(float(v),2) for v in box.xyxy[0].tolist()], mask_contours=[], mask_score=None, track_id=None) for i,box in enumerate(detection.boxes)]
            for obj in objects:
                obj['display_name'] = display_names.get(obj['label'], obj['label'])
            torch.cuda.synchronize(); t = time.perf_counter()
            if len(boxes):
                masks = segmenter.predict(bgr, bboxes=boxes.tolist(), device=0, imgsz=1024, verbose=False)[0]
                if masks.masks is None or len(masks.masks.data) != len(objects):
                    raise ValueError('Prompt/mask cardinality mismatch')
                for obj, mask in zip(objects, masks.masks.data.cpu().numpy()):
                    if mask.shape != (height,width):
                        mask = cv2.resize(mask.astype('uint8'),(width,height),interpolation=cv2.INTER_NEAREST)
                    contours, _ = cv2.findContours(mask.astype('uint8'), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
                    # Retain all contours including holes; SVG uses evenodd fill.
                    obj['mask_contours'] = [c.reshape(-1,2).tolist() for c in contours if len(c)>=3]
            torch.cuda.synchronize(); mask_ms = (time.perf_counter()-t)*1000
            t = time.perf_counter()
            hands_result = hand_model.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb),round(timestamp_ms))
            hand_ms = (time.perf_counter()-t)*1000
            hands = []
            for i, landmarks in enumerate(hands_result.hand_landmarks):
                category = hands_result.handedness[i][0]
                hands.append(dict(id=f'f{frame_index}-h{i}', handedness_model_output=category.category_name, handedness_score=round(category.score,5), points=[[round(p.x*width,2),round(p.y*height,2),round(p.z,6)] for p in landmarks], track_id=None))
            item = dict(frame_index=frame_index, timestamp_ms=timestamp_ms, presentation_seconds=pts, clip_pts=frame.pts, time_base=str(frame.time_base), source_timestamp_ms=round(source['parent_start_seconds']*1000+timestamp_ms,6), rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(), objects=objects, hands=hands, availability={'detection':'predicted','instance_segmentation':'box_prompted_prediction','hands':'predicted' if hands else 'no_detection','semantic_segmentation':'not_run','tracking':'not_run','ocr':'not_run','events':'not_run'}, latency_ms={'detector':round(det_ms,3),'segmenter':round(mask_ms,3),'hands':round(hand_ms,3)})
            frames.append(item)
            if len(frames) in [1,21,41,61]:
                cv2.imwrite(str(evidence / f'frame-{round(timestamp_ms):06d}.jpg'), bgr)
            if len(frames)%10==0: print(json.dumps({'frames':len(frames),'time_ms':timestamp_ms,'objects':len(objects),'hands':len(hands)}),flush=True)
    finally:
        hand_model.close(); clip.close()
    decode_elapsed = time.perf_counter()-decode_started
    shutil.copyfile(media/'clip.mp4',output/'clip.mp4')
    shutil.copyfile(media/'receipt.json',output/'producer-receipt.json')
    shutil.copyfile(model_receipt,output/'model-receipt.json')
    versions={n:importlib.metadata.version(n) for n in ['torch','torchvision','ultralytics','mediapipe','numpy','av']}
    result=dict(schema_version='labprism-video-result/1',created_at=datetime.now(timezone.utc).isoformat(),mode='offline_sampled_inference',prediction_status='unreviewed_model_proposals',source={**source,'clip_sha256':sha256(output/'clip.mp4')},video={'file':'clip.mp4','width':width,'height':height,'duration_ms':duration_ms,'sample_hz':sample_hz,'coordinate_system':'clip_pixels_top_left_xy','mirror_applied':False,'rotation_applied':False,'hand_z':'model_relative_wrist_depth_not_metric_global_3d'},models=[detector_info,mask_info,hand_info],environment={'python':platform.python_version(),'packages':versions,'gpu':torch.cuda.get_device_name(),'cuda':torch.version.cuda,'hand_provider':'CPU/XNNPACK','inference_batch':1,'detector_half':True,'seed':20260917},configuration={'detector_imgsz':960,'confidence':0.25,'iou':0.7,'max_det':100,'sam_imgsz':1024,'sam_prompts':'all_detector_boxes','temporal_mask_propagation':False,'hand_num_hands':2,'hand_thresholds':0.5},frames=frames,events=[],limitations=['diagnostic development clips; no independent ground truth','SAM masks depend on detector boxes and are per-frame, not video segmentation','handedness is raw model output, mirror convention unvalidated','unknown/undetected objects remain unknown; empty output is not background truth','no physical-contact, semantic, OCR, step or metric-3D claims'],metrics={'accuracy':None,'generalization':None,'temporal_quality':None,'npu_fps':None,'decoded_inference_wall_seconds':round(decode_elapsed,3),'processed_frames':len(frames),'sampled_pipeline_fps':round(len(frames)/decode_elapsed,3),'total_wall_seconds':round(time.perf_counter()-started,3),'peak_torch_allocated_mib':round(torch.cuda.max_memory_allocated()/2**20,1),'frames_with_hands':sum(bool(f['hands']) for f in frames),'module_warm_p50_ms':{key:round(float(np.median([f['latency_ms'][key] for f in frames[1:]])),3) for key in ['detector','segmenter','hands']}})
    validate_result(result)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    manifest={'schema_version':'labprism-inference-run/1','files':{p.name:sha256(p) for p in output.iterdir() if p.is_file()},'evidence':{p.name:sha256(p) for p in evidence.iterdir()},'source_sha256':source['source_sha256'],'model_receipt_sha256':sha256(model_receipt),**source_revision(Path(__file__).resolve().parents[3]),'implementation_sha256':sha256(__file__),'source_release':registry.get('source_release')}
    (output/'receipt.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(result['metrics']),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('media');p.add_argument('output');p.add_argument('--models',required=True)
    p.add_argument('--sample-hz',type=float,default=10)
    a=p.parse_args();run(a.media,a.output,a.models,a.sample_hz)

if __name__=='__main__': main()
