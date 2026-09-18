"""Measured model candidates on frozen baseline frames; no label or weight promotion."""
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
from labprism.tracking.association import Tracker, deduplicate_hands, reject_screen_conflicts


def run(baseline, output, model_receipt):
    import av
    import cv2
    import numpy as np
    import torch
    from rtmlib import RTMPose
    from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
    from ultralytics import YOLO

    baseline, output = Path(baseline), Path(output)
    parent = verify_run(baseline)
    registry = json.loads(Path(model_receipt).read_text())
    tasks = ['hand_landmarks_candidate','object_context_verification','semantic_segmentation']
    models = {task:next(m for m in registry['models'] if m['task']==task) for task in tasks}
    for model in models.values():
        if sha256(model['path']) != model['sha256']:raise ValueError('Candidate weight mismatch')
        for name, expected in model.get('auxiliary_files', {}).items():
            if Path(name).name!=name or sha256(Path(model['path']).parent/name)!=expected:raise ValueError('Candidate configuration mismatch')
    if not torch.cuda.is_available():raise RuntimeError('CUDA is required for context and semantic models')
    output.mkdir(parents=True, exist_ok=False)
    started=time.perf_counter()
    pose=RTMPose(models['hand_landmarks_candidate']['path'],model_input_size=(256,256),backend='onnxruntime',device='cpu')
    context=YOLO(models['object_context_verification']['path'])
    semantic_root=Path(models['semantic_segmentation']['path']).parent
    processor=SegformerImageProcessor.from_pretrained(semantic_root,local_files_only=True)
    semantic=SegformerForSemanticSegmentation.from_pretrained(semantic_root,local_files_only=True).eval().cuda()
    torch.cuda.reset_peak_memory_stats()
    object_tracker, hand_tracker=Tracker(),Tracker('hand')
    result=copy.deepcopy(parent);result['schema_version']='labprism-video-result/2'
    result['created_at']=datetime.now(timezone.utc).isoformat()
    result['derived_from']={'receipt_sha256':sha256(baseline/'receipt.json'),'result_sha256':sha256(baseline/'result.json'),'mode':'frozen_baseline_predictions_plus_causal_candidate_inference'}
    received=[]
    for original in parent['models']:
        matches=[m for m in registry['models'] if m['id']==original['id'] and m['sha256']==original['sha256']]
        if len(matches)!=1:raise ValueError('Parent model missing from received registry')
        candidate=matches[0]
        if {k:v for k,v in candidate.items() if k not in {'path','producer_receipt'}}!={k:v for k,v in original.items() if k not in {'path','producer_receipt'}}:
            raise ValueError('Parent model provenance differs')
        received.append(candidate)
    result['models']=received+list(models.values())
    result['configuration'].update(pipeline='candidate-v2',hand_keypoint_threshold=.3,hand_box_nms_iou=.5,screen_conflict_policy='retain_and_flag',screen_conflict_containment=.8,screen_conflict_confidence=.5,track_max_gap_ms=600,track_min_iou=.15,semantic_taxonomy='ADE20K-150',semantic_contour_epsilon_px=1.5)
    result['environment']['candidate_packages']={n:importlib.metadata.version(n) for n in ['rtmlib','onnxruntime','transformers','scipy']}
    result['environment']['hand_provider']='ONNXRuntime CPUExecutionProvider (RTMPose candidate)'
    result['video']['hand_z']='unavailable_2d_model'
    result['baseline_metrics']=copy.deepcopy(parent['metrics'])
    result['metrics']={key:None for key in ['accuracy','generalization','temporal_quality','npu_fps']}
    result['metrics']['processed_frames']=len(parent['frames'])
    result['events']=[]
    targets={f['frame_index']:f for f in result['frames']}
    processing_started=time.perf_counter();processed=0
    with av.open(str(baseline/'clip.mp4')) as clip:
        for index,decoded in enumerate(clip.decode(video=0)):
            if index not in targets:continue
            record=targets[index];rgb=decoded.to_ndarray(format='rgb24')
            if hashlib.sha256(rgb.tobytes()).hexdigest()!=record['rgb_sha256']:raise ValueError('Baseline frame bytes differ')
            bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
            stage={};t=time.perf_counter()
            prediction=context(bgr,device=0,imgsz=960,conf=.25,verbose=False)[0]
            candidates=[{'label':prediction.names[int(b.cls.item())],'confidence':round(float(b.conf.item()),5),'box':[round(float(v),2) for v in b.xyxy[0].tolist()]} for b in prediction.boxes]
            torch.cuda.synchronize();stage['context']=(time.perf_counter()-t)*1000
            record['context_objects']=candidates
            _,conflicts=reject_screen_conflicts(record['objects'],candidates)
            record['conflicting_objects']=conflicts
            record['rejected_objects']=[]
            by_id={obj['id']:obj['rejection'] for obj in conflicts}
            for obj in record['objects']:
                if obj['id'] in by_id:obj['model_conflict']=by_id[obj['id']]
            t=time.perf_counter();boxes=deduplicate_hands(record['objects'])
            keypoints,scores=pose(bgr,bboxes=[o['box'] for o in boxes]) if boxes else ([],[])
            hands=[];rejected=[]
            for i,(points,score,obj) in enumerate(zip(keypoints,scores,boxes)):
                hand={'id':f'f{index}-rh{i}','points':[[round(float(x),2),round(float(y),2),None] for x,y in points],
                      'point_scores':[round(float(x),6) for x in score], 'keypoint_threshold':.3,
                      'handedness_model_output':None,'handedness_score':None,'depth_available':False,
                      'box':obj['box'],'source_object_id':obj['id'],'model_id':models['hand_landmarks_candidate']['id'],
                      'median_point_score':round(float(np.median(score)),6),'track_id':None}
                if np.isfinite(points).all() and np.isfinite(score).all() and np.median(score)>=.3 and (score>=.3).sum()>=8:
                    hands.append(hand)
                else:rejected.append(dict(hand,reason='insufficient_keypoint_scores'))
            record['baseline_hands']=record['hands'];record['hands']=hands;record['rejected_hands']=rejected
            stage['hand_candidate']=(time.perf_counter()-t)*1000
            t=time.perf_counter()
            inputs=processor(images=rgb,return_tensors='pt').to('cuda')
            with torch.inference_mode():
                logits=semantic(**inputs).logits
                logits=torch.nn.functional.interpolate(logits,size=rgb.shape[:2],mode='bilinear',align_corners=False)
                probability,labelmap=logits.softmax(dim=1).max(dim=1)
                probability=probability[0].cpu().numpy();labelmap=labelmap[0].cpu().numpy().astype('uint8')
            map_name=f'semantic-{index:06d}.png'
            if not cv2.imwrite(str(output/map_name),labelmap):raise OSError('Semantic map write failed')
            regions=[]
            for label in np.unique(labelmap):
                mask=labelmap==label
                if mask.mean()<.005:continue
                contours,_=cv2.findContours(mask.astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
                contours=[cv2.approxPolyDP(c,1.5,True).reshape(-1,2).tolist() for c in contours]
                regions.append({'class_id':int(label),'label':semantic.config.id2label[int(label)],'mean_score':round(float(probability[mask].mean()),5),'mask_contours':[c for c in contours if len(c)>=3]})
            record['semantic_map']={'file':map_name,'sha256':sha256(output/map_name),'taxonomy':'ADE20K-150','ignore_value':None}
            record['semantic_regions']=regions
            stage['semantic']=(time.perf_counter()-t)*1000
            t=time.perf_counter();object_tracker.update(record['objects'],record['timestamp_ms'])
            hand_objects=[dict(label='hand_keypoints',box=h['box']) for h in hands]
            hand_tracker.update(hand_objects,record['timestamp_ms'])
            for hand,tracked in zip(hands,hand_objects):
                for name in ['track_id','track_state','track_gap_ms','trail']:hand[name]=tracked[name]
            stage['tracking']=(time.perf_counter()-t)*1000
            record['candidate_latency_ms']={k:round(v,3) for k,v in stage.items()}
            record['availability'].update(hands='predicted' if hands else 'no_detection',semantic_segmentation='predicted_ade20k',tracking='causal_association_candidate')
            processed+=1
            if processed%20==0:print(json.dumps({'frames':processed,'hands':len(hands),'rejected_objects':len(record['rejected_objects'])}),flush=True)
    if processed!=len(targets):raise ValueError('Missing baseline frames')
    elapsed=time.perf_counter()-processing_started
    result['metrics'].update(sampled_pipeline_fps=None,full_pipeline_latency_ms=None,candidate_processing_fps=round(processed/elapsed,3),candidate_wall_seconds=round(elapsed,3),
                             baseline_frames_with_hands=parent['metrics']['frames_with_hands'],frames_with_hands=sum(bool(f['hands']) for f in result['frames']),
                             rejected_balance_proposals=0,conflicting_balance_proposals=sum(len(f['conflicting_objects']) for f in result['frames']),object_tracks_created=object_tracker.next_id,hand_tracks_created=hand_tracker.next_id,
                             candidate_total_wall_seconds=round(time.perf_counter()-started,3),candidate_peak_torch_allocated_mib=round(torch.cuda.max_memory_allocated()/2**20,1))
    result['limitations']=['Candidate output coverage is not landmark accuracy or detection recall','Baseline detections and SAM masks are frozen inputs; candidate timing excludes their computation','RTMPose is 2D only; handedness unknown; low-score keypoints must stay hidden','Screen filtering failed regression; conflicting proposals are retained and flagged, not deleted','ADE20K semantic labels failed laboratory scene review; this layer is diagnostic only, not accepted segmentation','Causal IoU/motion tracking does not prove physical identity or contact; no masks or boxes are invented in gaps','No new training, independent quality, actions, OCR, video mask propagation, metric 3D or NPU claims','SegFormer weights restricted to research/evaluation; not cleared for commercial deployment']
    validate_result(result)
    for name in ['clip.mp4','producer-receipt.json']:shutil.copyfile(baseline/name,output/name)
    shutil.copyfile(baseline/'result.json',output/'baseline-result.json')
    shutil.copyfile(baseline/'receipt.json',output/'baseline-receipt.json')
    shutil.copyfile(model_receipt,output/'model-receipt.json')
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    manifest={'schema_version':'labprism-inference-run/1','files':{p.name:sha256(p) for p in output.iterdir() if p.is_file()},'evidence':{},'source_sha256':result['source']['source_sha256'],'model_receipt_sha256':sha256(model_receipt),**source_revision(Path(__file__).resolve().parents[3]),'implementation_sha256':sha256(__file__),'association_implementation_sha256':sha256(Path(__file__).resolve().parents[1]/'tracking/association.py'),'source_release':registry.get('source_release')}
    (output/'receipt.json').write_text(json.dumps(manifest,indent=2)+'\n')
    verify_run(output)
    print(json.dumps(result['metrics']),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('baseline');parser.add_argument('output');parser.add_argument('--models',required=True)
    args=parser.parse_args();run(args.baseline,args.output,args.models)
