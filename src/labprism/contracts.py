"""Semantic checks supplement the versioned JSON result contract."""
import math
import re


def validate_video_ocr_evidence(frame, result):
    """Optional v4 received-frame evidence; historical results remain readable."""
    ledger = result.get('ocr_integration', {})
    if ledger.get('schema_version') != 'labprism-video-ocr/1' or ledger.get('formal_readouts') is not False:
        raise ValueError('Video OCR evidence requires explicit integration provenance')
    receipts = {(row['sha256'], row['mode']) for row in ledger.get('receipts', [])}
    ids = set()
    for observation in frame['ocr_observations']:
        identity = observation.get('id')
        digest = observation.get('image_sha256', '')
        mode = observation.get('mode')
        basis = observation.get('region', {}).get('basis')
        if (not isinstance(identity, str) or not identity or identity in ids
                or not re.fullmatch('[a-f0-9]{64}', digest)
                or observation.get('image_file') != 'ocr-' + digest + '.png'
                or (observation.get('producer_receipt_sha256'), mode) not in receipts
                or mode not in {'automatic', 'manual'}
                or basis not in ({'whole_image', 'actual_panel_model_proposal'} if mode == 'automatic' else {'project_manual_review'})
                or observation.get('instrument_id') is not None or observation.get('field_values') != []
                or observation.get('status') != 'candidate'):
            raise ValueError('Invalid video OCR crop identity or association')
        ids.add(identity)
    for text in frame.get('texts', []):
        evidence = next((o for o in frame['ocr_observations'] if o['id'] == text.get('evidence_id')), None)
        if evidence is None or evidence['mode'] != 'automatic':
            raise ValueError('Automatic text layer cannot use a manual diagnostic')


def validate_result(result):
    if result['schema_version'] not in {'labprism-video-result/1','labprism-video-result/2','labprism-video-result/3','labprism-video-result/4'}:
        raise ValueError('Unsupported result schema')
    source, video = result['source'], result['video']
    modern = result['schema_version'] == 'labprism-video-result/4'
    if modern:
        validate_v4_metadata(result)
    if (not modern and source['split'] not in {'train', 'val'}) or source['camera_role'] not in ({'first_person', 'third_person', 'unknown'} if modern else {'first_person', 'third_person'}):

        raise ValueError('Development result requires known role and development split')
    width, height = video['width'], video['height']
    if width <= 0 or height <= 0 or video['coordinate_system'] != 'clip_pixels_top_left_xy':
        raise ValueError('Invalid dimensions/coordinates')
    previous_time, previous_index = -1, -1
    for frame in result['frames']:
        if frame.get('ocr_observations'):
            validate_video_ocr_evidence(frame, result)
        t, index = frame['timestamp_ms'], frame['frame_index']
        if not math.isfinite(t) or not previous_time < t < video['duration_ms'] or index <= previous_index:
            raise ValueError('Frames must increase strictly within the clip')
        if abs(frame['source_timestamp_ms'] - (source['parent_start_seconds']*1000+t)) > 1:
            raise ValueError('Source/clip timestamp lineage mismatch')
        if modern:
            from fractions import Fraction
            media_ms = float(frame['clip_pts'] * Fraction(frame['time_base']) * 1000)
            if abs(media_ms - result['time_mapping']['clip_origin_ms'] - t) > .01:
                raise ValueError('PTS/timebase differs from clip timestamp')
        previous_time, previous_index = t, index
        ids = set()
        for obj in frame['objects']:
            if obj['id'] in ids: raise ValueError('Duplicate frame instance')
            ids.add(obj['id'])
            x1,y1,x2,y2 = obj['box']
            if not 0 <= x1 < x2 <= width or not 0 <= y1 < y2 <= height:
                raise ValueError('Invalid box in clip coordinates')
            if not 0 <= obj['confidence'] <= 1: raise ValueError('Invalid confidence')
            if 'display_name' in obj and (not isinstance(obj['display_name'], str) or not obj['display_name'].strip()):
                raise ValueError('Invalid object display name')
            if 'ontology' in result:
                ontology = result['ontology']
                expected = ontology.get('display_names', {}).get(obj.get('label'), obj.get('label'))
                if obj.get('display_name') != expected:
                    raise ValueError('Object display name differs from ontology')
            for contour in obj['mask_contours']:
                if len(contour) < 3 or any(not(0 <= x < width and 0 <= y < height) for x,y in contour):
                    raise ValueError('Invalid mask contour')
        for hand in frame['hands']:
            is_2d=result['schema_version'] in {'labprism-video-result/2','labprism-video-result/3','labprism-video-result/4'} and hand.get('depth_available') is False
            if len(hand['points']) != 21 or any(len(p)!=3 or any(not math.isfinite(v) for v in p[:2]) or (p[2] is not None if is_2d else not isinstance(p[2],(int,float)) or not math.isfinite(p[2])) for p in hand['points']):
                raise ValueError('Hand requires 21 finite xyz points')
            if is_2d and (len(hand.get('point_scores',[]))!=21 or any(not math.isfinite(s) for s in hand['point_scores'])):
                raise ValueError('2D hand requires 21 finite model scores')
        semantic=frame.get('semantic_map')
        if semantic:
            if (result['schema_version'] not in {'labprism-video-result/2','labprism-video-result/3','labprism-video-result/4'} or semantic['taxonomy'] != (result['semantic_taxonomy']['id'] if modern else 'ADE20K-150')
                    or not re.fullmatch(r'semantic-[0-9]+\.png',semantic['file'])
                    or not re.fullmatch(r'[0-9a-f]{64}',semantic['sha256'])):
                raise ValueError('Invalid semantic map identity')
        labels=set()
        for region in frame.get('semantic_regions',[]):
            label=region['class_id']
            if not semantic or not isinstance(label,int) or label not in ({c['id'] for c in result['semantic_taxonomy']['classes']} if modern else set(range(150))) or label in labels or not 0<=region['mean_score']<=1:
                raise ValueError('Invalid or duplicate semantic class')
            labels.add(label)
            for contour in region['mask_contours']:
                if len(contour)<3 or any(not(0<=x<width and 0<=y<height) for x,y in contour):
                    raise ValueError('Invalid semantic contour')
        for group in [frame['objects'],frame['hands']]:
            tracks=[o.get('track_id') for o in group if o.get('track_id') is not None]
            if len(tracks)!=len(set(tracks)):raise ValueError('Duplicate track identity in a frame')
            for obj in group:
                times=[]
                for pt in obj.get('trail',[]):
                    if len(pt)!=3 or any(not math.isfinite(v) for v in pt) or pt[0]>t:raise ValueError('Invalid or future track point')
                    times.append(pt[0])
                if any(a>=b for a,b in zip(times,times[1:])):raise ValueError('Track times must increase')
        if result['schema_version'] in {'labprism-video-result/3','labprism-video-result/4'}:
            temporal_ids=set()
            for item in frame.get('temporal_instances',[]):
                if (item['id'] in temporal_ids or item['seed_frame_index']>index
                        or item['state'] not in {'prompted','memory_propagated'}
                        or item['confidence'] is not None or item['status']!='unreviewed_model_proposal'
                        or not isinstance(item['visible_pixels'],int) or not 0<=item['visible_pixels']<=width*height
                        or not re.fullmatch(r'temporal-[0-9]+-[0-9]+\.png',item['mask']['file'])
                        or not re.fullmatch(r'[0-9a-f]{64}',item['mask']['sha256'])):
                    raise ValueError('Invalid temporal mask identity')
                temporal_ids.add(item['id'])
                for contour in item['mask_contours']:
                    if len(contour)<3 or any(not(0<=x<width and 0<=y<height) for x,y in contour):
                        raise ValueError('Invalid temporal mask contour')
            text_ids=set()
            for item in frame.get('texts',[]):
                if (item['id'] in text_ids or not isinstance(item['text'],str) or not item['text'].strip()
                        or not 0<=item['score']<=1 or len(item['quad'])!=4
                        or any(len(p)!=2 or not(0<=p[0]<width and 0<=p[1]<height) for p in item['quad'])
                        or item['status']!='unreviewed_model_proposal' or item['numeric_value'] is not None
                        or item['unit'] is not None):
                    raise ValueError('Invalid OCR observation')
                text_ids.add(item['id'])
            if frame.get('texts') and frame['availability']['ocr']!='predicted':
                raise ValueError('OCR availability contradicts observations')
            objects={o['id']:o for o in frame['objects']}
            hands={h['id']:h for h in frame['hands']}
            for relation in frame.get('relations',[]):
                obj=objects.get(relation['object_id']);hand=hands.get(relation['hand_id'])
                if (not obj or not hand or relation['physical_contact'] is not None
                        or relation['type']!='hand_object_proximity_2d'
                        or relation['object_track_id']!=obj.get('track_id')
                        or relation['hand_track_id']!=hand.get('track_id')
                        or not 0<=relation['distance_px']<=relation['threshold_px']):
                    raise ValueError('Invalid or unbound proximity observation')
                from labprism.understanding.proximity import point_box_distance
                index=relation['keypoint_index']
                if (index not in (4,8,12,16,20)
                        or hand.get('point_scores',[1.]*21)[index]<hand.get('keypoint_threshold',.3)
                        or abs(point_box_distance(hand['points'][index],obj['box'])-relation['distance_px'])>.001):
                    raise ValueError('Proximity must bind a score-qualified observed fingertip')
    if not result['frames']: raise ValueError('Empty analysis')
    if 'ontology' in result:
        ontology = result['ontology']
        if (ontology.get('schema_version') != 'labprism-ontology/1'
                or ontology.get('display_language') != 'zh-CN'
                or not isinstance(ontology.get('display_names'), dict)
                or any(not isinstance(key, str) or not key or not isinstance(value, str) or not value.strip()
                       for key, value in ontology['display_names'].items())):
            raise ValueError('Invalid result ontology')
    if result['schema_version'] in {'labprism-video-result/3','labprism-video-result/4'}:
        frames={f['frame_index']:f for f in result['frames']};event_ids=set()
        for frame in frames.values():
            for item in frame.get('temporal_instances',[]):
                seed=frames.get(item['seed_frame_index'])
                if not seed or not any(o['id']==item['seed_object_id'] and o['label']==item['label'] for o in seed['objects']):
                    raise ValueError('Temporal mask prompt is not bound to a real detection')
        for event in result.get('events',[]):
            if (event['id'] in event_ids or event['type']!='hand_object_proximity_2d'
                    or not 0<=event['start_ms']<event['end_ms']<video['duration_ms']
                    or event['physical_contact'] is not None or event['step'] is not None
                    or event['status']!='unreviewed_geometric_proposal' or len(event['evidence'])<4):
                raise ValueError('Invalid proximity event')
            event_ids.add(event['id']);times=[]
            for observation in event['evidence']:
                frame=frames.get(observation['frame_index'])
                if not frame or observation['timestamp_ms']!=frame['timestamp_ms']:
                    raise ValueError('Event points to missing frame')
                matches=[r for r in frame.get('relations',[]) if r['hand_id']==observation['hand_id']
                         and r['object_id']==observation['object_id']
                         and r['hand_track_id']==event['hand_track_id'] and r['object_track_id']==event['object_track_id']
                         and r['keypoint_index']==observation['keypoint_index'] and r['distance_px']==observation['distance_px']]
                if len(matches)!=1:raise ValueError('Event evidence is not bound to a frame relation')
                times.append(frame['timestamp_ms'])
            if times[0]!=event['start_ms'] or times[-1]!=event['end_ms'] or any(a>=b for a,b in zip(times,times[1:])):
                raise ValueError('Event interval differs from observed evidence')
    return result


def validate_v4_metadata(result):
    source = result['source']
    purpose = result.get('data_use', {}).get('purpose')
    split = source.get('split')
    if purpose == 'production_observation':
        if split is not None: raise ValueError('Production observations have no training split')
    elif purpose == 'development':
        if split not in {'train','val'}: raise ValueError('Development cannot consume sealed tests')
    elif purpose == 'evaluation':
        if split not in {'train','val','test','holdout'}: raise ValueError('Evaluation requires original split')
    else: raise ValueError('Unknown data purpose')
    taxonomy = result.get('semantic_taxonomy', {})
    if not taxonomy.get('id') or not taxonomy.get('version') or not isinstance(taxonomy.get('classes'),list):
        raise ValueError('Versioned taxonomy required')
    ids = [c['id'] for c in taxonomy['classes']]
    if len(ids) != len(set(ids)) or any(type(i) is not int or i<0 for i in ids):
        raise ValueError('Invalid taxonomy classes')
    if taxonomy.get('ignore_id') in ids: raise ValueError('Ignore is not an evaluated class')
    mapping = result.get('time_mapping', {})
    if not isinstance(mapping.get('clip_origin_ms'),(int,float)) or not math.isfinite(mapping['clip_origin_ms']):
        raise ValueError('Explicit PTS origin required')
    for key in ('capture_origin_ms','global_origin_ms'):
        if key not in mapping or (mapping[key] is not None and not math.isfinite(mapping[key])):
            raise ValueError('Unknown clocks must remain null')
    geometry = result.get('coordinates', {})
    from labprism.geometry.transforms import transform_points
    transform_points([[0,0]], geometry.get('clip_to_source'))
    if not isinstance(geometry.get('operations'),list): raise ValueError('Coordinate lineage required')
    statuses = result.get('output_statuses', {})
    frames = result.get('frames', [])
    present = {
        'boxes': any(f.get('objects') for f in frames),
        'instance_masks': any(o.get('mask_contours') for f in frames for o in f.get('objects', [])),
        'semantic_map': any(f.get('semantic_map') for f in frames),
        'keypoints': any(f.get('hands') for f in frames),
        'tracks': any(o.get('track_id') for f in frames for o in [*f.get('objects', []), *f.get('hands', [])]),
        'relations': any(f.get('relations') for f in frames),
        'events': bool(result.get('events')),
        'readouts': bool(result.get('readouts')),
    }
    for name in ('boxes','instance_masks','semantic_map','keypoints','tracks','relations','events','readouts'):
        value = statuses.get(name,{})
        if value.get('state') not in {'predicted','no_detection','not_run','not_connected','failed','not_applicable'} or not value.get('reason'):
            raise ValueError('Each output needs independent state and reason')
        if present[name] and value['state'] != 'predicted':
            raise ValueError(f'{name} contains output but is declared unavailable')
    return result
