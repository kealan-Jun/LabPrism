#!/usr/bin/env python3
"""Replay received joint segmentation on every exact sampled parent video frame."""
import argparse,copy,fcntl,hashlib,json,os,shutil,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from labprism.artifacts import sha256,verify_run,freeze_sources
from labprism.contracts import validate_result
from labprism.perception.trained_hand import verify_decoded_frame
from labprism.perception.trained_segmentation import JointSegmenter

def run(request_path,output):
 import av,cv2,numpy as np,torch
 request=json.loads(request_path.read_text());repo=Path(__file__).resolve().parents[1];config=json.loads((repo/'configs/project.json').read_text());nas=Path(os.environ.get('LABPRISM_NAS_ROOT',config['nas_root_default'])).resolve();output.resolve().relative_to(nas)
 marker=json.loads((nas/'.labprism-volume.json').read_text());assert marker['volume_id']==config['nas_volume_id']
 mounts=json.loads(subprocess.check_output(['findmnt','-J','-T',str(nas),'-o','FSTYPE'],text=True));assert any(r['fstype'] in {'cifs','nfs','nfs4'} for r in mounts['filesystems'])
 parent_path=Path(request['parent']['path'])
 for name in ['result','receipt']:
  if sha256(parent_path/(name+'.json'))!=request['parent'][name+'_sha256']:raise ValueError('Frozen input changed')
 parent=verify_run(parent_path);producer=Path(request['producer_receipt']['path'])
 if sha256(producer)!=request['producer_receipt']['sha256']:raise ValueError('Producer receipt changed')
 m=request['model'];handoff=json.loads(producer.read_text())
 if handoff['checkpoint']['sha256']!=m['sha256'] or handoff['role']!=m['role']:raise ValueError('Model/producer mismatch')
 lock=Path(request['gpu_lock']).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<3*1024**3:raise RuntimeError('Insufficient CUDA memory')
 torch.set_num_threads(4);cv2.setNumThreads(2);inference=request.get('inference',{});model=JointSegmenter(m['path'],m['sha256'],m['role'],parent['source']['camera_role'],imgsz=inference.get('imgsz',640),mask_decode=inference.get('mask_decode','native_logits'));output.mkdir(parents=True,exist_ok=False);evidence=output/'evidence';evidence.mkdir()
 archive=Path(config['data_root_default'])/'source-snapshots'/('joint-segmentation-'+sha256(request_path)+'.zip');implementation=freeze_sources(repo,[Path(__file__),*sorted((repo/'src/labprism').rglob('*.py'))],archive)
 for source,dest in [(parent_path/'clip.mp4','clip.mp4'),(parent_path/'producer-receipt.json','producer-receipt.json'),(parent_path/'result.json','baseline-result.json'),(parent_path/'receipt.json','baseline-receipt.json'),(producer,'training-handoff.json')]:shutil.copyfile(source,output/dest)
 registry={'schema_version':'labprism-model-receipt/1','models':[m]};(output/'model-receipt.json').write_text(json.dumps(registry));(output/'request.json').write_text(json.dumps(request,indent=2))
 display=json.loads((repo/'configs/models/class-display-names.json').read_text());result={k:copy.deepcopy(parent[k]) for k in ['source','video']};w,h=parent['video']['width'],parent['video']['height'];sw,sh=parent['source']['source_dimensions'];result.update(schema_version='labprism-video-result/4',created_at=datetime.now(timezone.utc).isoformat(),mode='offline_sampled_inference',prediction_status='unreviewed_model_proposals',data_use={'purpose':'development'},time_mapping=copy.deepcopy(parent.get('time_mapping',{'clip_origin_ms':0,'capture_origin_ms':None,'global_origin_ms':None})),coordinates=copy.deepcopy(parent.get('coordinates',{'clip_to_source':[[sw/w,0,0],[0,sh/h,0],[0,0,1]],'operations':[]})),ontology={'schema_version':'labprism-ontology/1','display_names':display,'display_language':'zh-CN'},semantic_taxonomy={'id':'visioncortex-lab-v1','version':'1','classes':[{'id':int(k),'label':v} for k,v in model.names.items()],'ignore_id':255,'unknown_id':None},models=[m],frames=[],events=[],output_statuses={k:{'state':'predicted' if k in ['boxes','instance_masks'] else 'not_run','reason':'Current-frame joint model prediction' if k in ['boxes','instance_masks'] else 'Isolated segmentation inspection; other modules remain available in parent run'} for k in ['boxes','instance_masks','semantic_map','keypoints','tracks','relations','events','readouts']},derived_from={'result_sha256':sha256(parent_path/'result.json'),'receipt_sha256':sha256(parent_path/'receipt.json'),'mode':'same_video_pts_pixels_joint_segmentation_candidate'},configuration={'imgsz':model.imgsz,'mask_grid':[model.imgsz//4,model.imgsz//4],'mask_decode':model.mask_decode,'confidence':.25,'nms_iou':.55,'batch':1,'precision':'FP32','semantic_auxiliary_head_exposed':False,'mask_temporal_propagation':False},environment={'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)},limitations=['Research candidate; not production promotion','Existing development footage includes training exposure; no independent generalization claim','Prototype grid is recorded in configuration; native_logits mode upsamples logits before thresholding; contours preserve holes using evenodd rendering','No hand pose, tracking, OCR, events or physical relationships inferred in this isolated run','Auxiliary semantic head lacks background supervision and is not exposed as full-image semantics'])
 targets={f['frame_index']:f for f in parent['frames']};times=[];start=time.perf_counter();seen=set();snapshots=set(request.get('evidence_frame_indexes',[0]))
 with av.open(str(parent_path/'clip.mp4')) as clip:
  for index,decoded in enumerate(clip.decode(video=0)):
   if index not in targets:continue
   original=targets[index];rgb=decoded.to_ndarray(format='rgb24');verify_decoded_frame(original,rgb,decoded.pts,decoded.time_base,[w,h])
   torch.cuda.synchronize();t=time.perf_counter();objects=model.predict(rgb);torch.cuda.synchronize();ms=(time.perf_counter()-t)*1000;times.append(ms)
   for i,obj in enumerate(objects):obj.update(id=f'f{index}-joint-o{i}',display_name=display.get(obj['label'],obj['label']),model_id=m['id'])
   frame={k:copy.deepcopy(original[k]) for k in ['frame_index','timestamp_ms','presentation_seconds','clip_pts','time_base','source_timestamp_ms','rgb_sha256'] if k in original};frame.update(objects=objects,hands=[],availability={'detection':'predicted','instance_segmentation':'joint_model_prediction','hands':'not_run','semantic_segmentation':'not_run','tracking':'not_run','ocr':'not_run','events':'not_run'},latency_ms={'joint_detection_masks':ms});result['frames'].append(frame);seen.add(index)
   if index in snapshots:
    shown=rgb.copy()
    for obj in objects:
     mask=np.zeros((h,w),np.uint8);cv2.drawContours(mask,[np.asarray(c,np.int32) for c in obj['mask_contours']],-1,1,cv2.FILLED);shown[mask>0]=(shown[mask>0]*.7+np.array([50,220,170])*.3).astype(np.uint8)
    cv2.imwrite(str(evidence/f'frame-{index:06d}.jpg'),shown[:,:,::-1]);cv2.imwrite(str(evidence/f'original-{index:06d}.jpg'),rgb[:,:,::-1])
   if len(seen)%100==0:print(json.dumps({'frames':len(seen),'objects':len(objects),'time_ms':frame['timestamp_ms']}),flush=True)
 if seen!=set(targets):raise ValueError('Incomplete decode; no accepted run receipt')
 elapsed=time.perf_counter()-start;result['metrics']={'processed_frames':len(seen),'observations':sum(len(f['objects']) for f in result['frames']),'processing_seconds':elapsed,'processing_fps':len(seen)/elapsed,'joint_p50_ms':float(np.median(times[1:])),'joint_p95_ms':float(np.percentile(times[1:],95)),'scope':'decode + joint detection/masks + contour serialization and selected evidence; not full laboratory pipeline','accuracy':None,'generalization':None,'temporal_quality':None,'full_pipeline_fps':None,'npu_fps':None};validate_result(result);(output/'result.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')));receipt={'schema_version':'labprism-inference-run/1','files':{p.name:sha256(p) for p in output.iterdir() if p.is_file()},'evidence':{p.name:sha256(p) for p in evidence.iterdir()},'source_sha256':result['source']['source_sha256'],'model_receipt_sha256':sha256(output/'model-receipt.json'),'implementation':implementation,'promotion':'none'};(output/'receipt.json').write_text(json.dumps(receipt,indent=2));verify_run(output);print(json.dumps(result['metrics']),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.request,a.output)
