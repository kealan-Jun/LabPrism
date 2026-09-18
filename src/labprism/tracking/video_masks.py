"""SAM2 temporal-memory masks on verified sampled frames, with bounded reseeding."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time

from labprism.artifacts import sha256, verify_run
from labprism.contracts import validate_result
from labprism.perception.baseline import source_revision


def contours(mask):
    import cv2
    found,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    polygons=[]
    for contour in found:
        if len(contour)<3:
            continue
        polygon=cv2.approxPolyDP(contour,1.,True).reshape(-1,2)
        # Polygon approximation can collapse a tiny component to a line or point.
        if len(polygon)>=3:
            polygons.append(polygon.tolist())
    return polygons


def run(parent_directory, output, window_frames=50, max_objects=3):
    import av
    import cv2
    import numpy as np
    import torch
    from ultralytics.models.sam import SAM2VideoPredictor
    from ultralytics.utils import ops

    if not 1<=max_objects<=8 or not 2<=window_frames<=100:
        raise ValueError('Bounded video memory requires 1–8 objects and 2–100 frames per window')
    parent_directory,output=Path(parent_directory),Path(output)
    parent=verify_run(parent_directory)
    if parent['schema_version']!='labprism-video-result/3':
        raise ValueError('Temporal stage requires continuous v3 parent')
    model=next(m for m in parent['models'] if m['task']=='box_prompted_instance_segmentation')
    if sha256(model['path'])!=model['sha256']:
        raise ValueError('SAM model identity mismatch')
    if not torch.cuda.is_available():
        raise RuntimeError('Temporal recipe requires CUDA')
    output.mkdir(parents=True,exist_ok=False)
    result=copy.deepcopy(parent)
    result['created_at']=datetime.now(timezone.utc).isoformat()
    result['derived_from']={'result_sha256':sha256(parent_directory/'result.json'),
                            'receipt_sha256':sha256(parent_directory/'receipt.json')}
    result['configuration'].update(temporal_mask_propagation=True,temporal_window_frames=window_frames,
        temporal_max_objects=max_objects,temporal_seed_policy='highest_confidence_non_hand_boxes_at_window_start')
    result['temporal_windows']=[]
    for frame in result['frames']:
        frame['temporal_instances']=[]
        frame['availability']['video_segmentation']='not_prompted'
    width,height=parent['video']['width'],parent['video']['height']
    frames=result['frames'];targets={f['frame_index']:f for f in frames}
    predictor=SAM2VideoPredictor(overrides={'model':model['path'],'imgsz':1024,'device':0,
        'verbose':False,'save':False,'task':'segment','mode':'predict','vid_stride':1})
    started=time.perf_counter();processed=0
    with tempfile.TemporaryDirectory(prefix='labprism-temporal-') as temporary:
        temporary=Path(temporary)
        # FFV1 is lossless; its decoded RGB is checked against the source before propagation.
        paths=[];writer=None
        with av.open(str(parent_directory/'clip.mp4')) as container:
            for index,decoded in enumerate(container.decode(video=0)):
                if index not in targets:continue
                rgb=decoded.to_ndarray(format='rgb24')
                if hashlib.sha256(rgb.tobytes()).hexdigest()!=targets[index]['rgb_sha256']:
                    raise ValueError('Source RGB mismatch')
                if processed%window_frames==0:
                    if writer is not None:writer.release()
                    path=temporary/f'window-{len(paths):04d}.avi';paths.append(path)
                    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'FFV1'),parent['video']['sample_hz'],(width,height))
                    if not writer.isOpened():raise RuntimeError('Lossless sampled video writer unavailable')
                writer.write(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR));processed+=1
        if writer is not None:writer.release()
        if processed!=len(frames):raise ValueError('Missing sampled frames')
        for window,path in enumerate(paths):
            subset=frames[window*window_frames:(window+1)*window_frames]
            prompts=sorted((o for o in subset[0]['objects'] if o['label'] not in {'hand','gloved_hand'}),
                           key=lambda o:-o['confidence'])[:max_objects]
            if not prompts:continue
            # Every temporary frame maps to an exact parent PTS/RGB identity.
            with av.open(str(path)) as check:
                decoded_count=0
                for i,decoded in enumerate(check.decode(video=0)):
                    if i>=len(subset) or hashlib.sha256(decoded.to_ndarray(format='rgb24').tobytes()).hexdigest()!=subset[i]['rgb_sha256']:
                        raise ValueError('Lossless temporal input differs from source')
                    decoded_count+=1
                if decoded_count!=len(subset):raise ValueError('Incomplete temporal window')
            predictor.inference_state={}
            record={'id':f'window-{window}','first_frame_index':subset[0]['frame_index'],
                'last_frame_index':subset[-1]['frame_index'],'source_frame_indices':[f['frame_index'] for f in subset],
                'prompt_ids':[p['id'] for p in prompts],'sampled_input_sha256':sha256(path),
                'identity_across_windows':False}
            result['temporal_windows'].append(record)
            count=0
            for offset,prediction in enumerate(predictor(source=str(path),bboxes=[o['box'] for o in prompts],stream=True)):
                frame=subset[offset]
                state=predictor.inference_state;current=state['output_dict']
                frame_number=predictor.dataset.frame
                raw=current['cond_frame_outputs'].get(frame_number)
                if raw is None:raw=current['non_cond_frame_outputs'][frame_number]
                logits=raw['pred_masks'].flatten(0,1)
                if len(logits)!=len(prompts):raise ValueError('Temporal object identity count changed')
                masks=ops.scale_masks(logits[None].float(),(height,width),padding=False)[0]
                masks=(masks>predictor.model.mask_threshold).cpu().numpy().astype('uint8')
                for j,(prompt,mask) in enumerate(zip(prompts,masks)):
                    name=f'temporal-{frame["frame_index"]:06d}-{j:02d}.png'
                    if not cv2.imwrite(str(output/name),mask):raise OSError('Mask write failed')
                    frame['temporal_instances'].append({'id':f'w{window}-object{j}',
                        'label':prompt['label'],'display_name':prompt.get('display_name',prompt['label']),
                        'seed_frame_index':subset[0]['frame_index'],'seed_object_id':prompt['id'],
                        'state':'prompted' if offset==0 else 'memory_propagated','visible_pixels':int(mask.sum()),
                        'mask_contours':contours(mask),'mask':{'file':name,'sha256':sha256(output/name)},
                        'confidence':None,'status':'unreviewed_model_proposal'})
                frame['availability']['video_segmentation']='sam2_memory_candidate'
                count+=1
            if count!=len(subset):raise ValueError('Temporal predictor skipped frames')
            print(json.dumps({'window':window,'frames':count,'seed_objects':len(prompts)}),flush=True)
    result['parent_metrics']=parent['metrics']
    result['metrics']={'accuracy':None,'generalization':None,'temporal_quality':None,'npu_fps':None,
        'temporal_stage_wall_seconds':round(time.perf_counter()-started,3),
        'processed_frames':len(frames),'frames_with_hands':sum(bool(f['hands']) for f in frames),
        'temporal_frames':sum(bool(f['temporal_instances']) for f in frames),
        'temporal_windows':len(result['temporal_windows']),'video_mask_accuracy':None}
    result['limitations'] += ['SAM2 video masks use temporal memory on sampled frames, up to three detector prompts per window',
        'Temporal identities reset at each window; no across-window or physical identity claim',
        'No calibrated mask confidence; blank masks remain empty; propagated false positives/drift require review']
    validate_result(result)
    for name in ['clip.mp4','producer-receipt.json','model-receipt.json']:
        shutil.copyfile(parent_directory/name,output/name)
    for name in ['result.json','receipt.json']:
        shutil.copyfile(parent_directory/name,output/f'baseline-{name}')
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    receipt={'schema_version':'labprism-inference-run/1',
        'files':{p.name:sha256(p) for p in output.iterdir() if p.is_file()},'evidence':{},
        'source_sha256':result['source']['source_sha256'],
        'model_receipt_sha256':sha256(output/'model-receipt.json'),
        **source_revision(Path(__file__).resolve().parents[3]),'implementation_sha256':sha256(__file__)}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');verify_run(output)
    print(json.dumps(result['metrics']),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent');parser.add_argument('output')
    parser.add_argument('--window-frames',type=int,default=50);parser.add_argument('--max-objects',type=int,default=3)
    args=parser.parse_args();run(args.parent,args.output,args.window_frames,args.max_objects)
