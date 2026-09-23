"""Bounded browser projections of immutable results; original receipts stay local."""
import copy
import hashlib
import json
from pathlib import Path
from labprism.contracts import validate_result


def browser_projection(result):
    """Allowlisted metadata; no private filesystem paths or execution commands."""
    out={k:copy.deepcopy(result[k]) for k in ['schema_version','created_at','video','ontology','events','metrics',
         'temporal_windows','data_use','semantic_taxonomy','time_mapping','coordinates','output_statuses','ocr_integration'] if k in result}
    out['source']={k:copy.deepcopy(v) for k,v in result['source'].items() if k in {
        'source_id','source_sha256','clip_sha256','source_group','split','camera_id','camera_role',
        'baseline_exposure','parent_start_seconds','source_dimensions','complete_source_file',
        'public_release_authorized','label_revision','independent_ground_truth'}}
    out['source']['experiment']={k:v for k,v in result['source'].get('experiment',{}).items()
        if k in {'experiment_id','experiment_title','recording_date'}}
    out['models']=[{k:v for k,v in model.items() if k in {'id','task','sha256','parent_sha256','role','license','backend','hash_basis'}} for model in result['models']]
    replay=result.get('configuration',{}).get('trained_hand_replay')
    if replay:
        out['model_usage']={'hand_pose':replay['model_id']}
    out['environment']={k:v for k,v in result.get('environment',{}).items() if k in {'gpu','hand_provider','actual_execution_providers'}}
    out['projection']='local_inspection_metadata; original artifact retained by hash'
    return out


def write_chunks(result, destination, *, seconds=5, max_frames=50):
    validate_result(result)
    if not 0<seconds<=30 or not 1<=max_frames<=100:raise ValueError('Unbounded chunk configuration')
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    header=browser_projection(result);chunks=[];batch=[]
    def flush():
        if not batch:return
        name=f'frames-{len(chunks):05d}.json'
        raw=json.dumps({'schema_version':'labprism-frame-chunk/1','frames':batch},ensure_ascii=False,separators=(',',':')).encode()
        (destination/name).write_bytes(raw)
        chunks.append({'file':name,'start_ms':batch[0]['timestamp_ms'],'end_ms':batch[-1]['timestamp_ms'],
                       'count':len(batch),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                       'times_ms':[f['timestamp_ms'] for f in batch]})
    for frame in result['frames']:
        if batch and (len(batch)>=max_frames or frame['timestamp_ms']-batch[0]['timestamp_ms']>=seconds*1000):flush();batch=[]
        batch.append(frame)
    flush()
    header.update(schema_version='labprism-result-index/1',result_schema_version=result['schema_version'],
                  frame_count=len(result['frames']),chunks=chunks,
                  layers={k:any(bool(f.get(v)) for f in result['frames']) for k,v in {'semantic':'semantic_regions','ocr':'texts','temporal':'temporal_instances'}.items()})
    header['layers'].update(
        masks=any(o.get('mask_contours') for f in result['frames'] for o in f['objects']),
        hands=any(f['hands'] for f in result['frames']),
        trails=any(o.get('track_id') for f in result['frames'] for o in [*f['objects'],*f['hands']]))
    # Evidence is already in the frame chunks and full download. Navigation must
    # not eagerly duplicate every relation from an arbitrarily long experiment.
    events=result.get('events',[])
    header['events']=[{**{k:v for k,v in event.items() if k!='evidence'},
                       'evidence_count':len(event.get('evidence',[]))}
                      for event in events[:2000]]
    header['event_count']=len(events)
    header['events_truncated']=len(events)>2000
    # Small textual navigation, no per-frame images/contours in the index.
    header['text_index']=[{'text':t['text'],'score':t['score'],'timestamp_ms':f['timestamp_ms']}
                          for f in result['frames'] for t in f.get('texts',[])][:2000]
    header['text_index_truncated']=sum(len(f.get('texts',[])) for f in result['frames'])>2000
    header['ocr_frame_index']=[{'timestamp_ms':f['timestamp_ms'],
        'automatic':sum(o['mode']=='automatic' for o in f['ocr_observations']),
        'manual':sum(o['mode']=='manual' for o in f['ocr_observations'])}
        for f in result['frames'] if f.get('ocr_observations')][:2000]
    header['ocr_frame_index_truncated']=sum(bool(f.get('ocr_observations')) for f in result['frames'])>2000
    (destination/'index.json').write_text(json.dumps(header,ensure_ascii=False,separators=(',',':')))
    full=browser_projection(result);full['frames']=result['frames']
    (destination/'result.json').write_text(json.dumps(full,ensure_ascii=False,separators=(',',':')))
    return header
