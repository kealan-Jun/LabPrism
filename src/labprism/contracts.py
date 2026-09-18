"""Semantic checks supplement the versioned JSON result contract."""
import math
import re


def validate_result(result):
    if result['schema_version'] not in {'labprism-video-result/1','labprism-video-result/2','labprism-video-result/3'}:
        raise ValueError('Unsupported result schema')
    source, video = result['source'], result['video']
    if source['split'] not in {'train', 'val'} or source['camera_role'] not in {'first_person', 'third_person'}:
        raise ValueError('Development result requires known role and development split')
    width, height = video['width'], video['height']
    if width <= 0 or height <= 0 or video['coordinate_system'] != 'clip_pixels_top_left_xy':
        raise ValueError('Invalid dimensions/coordinates')
    previous_time, previous_index = -1, -1
    for frame in result['frames']:
        t, index = frame['timestamp_ms'], frame['frame_index']
        if not math.isfinite(t) or not previous_time < t < video['duration_ms'] or index <= previous_index:
            raise ValueError('Frames must increase strictly within the clip')
        if abs(frame['source_timestamp_ms'] - (source['parent_start_seconds']*1000+t)) > 1:
            raise ValueError('Source/clip timestamp lineage mismatch')
        previous_time, previous_index = t, index
        ids = set()
        for obj in frame['objects']:
            if obj['id'] in ids: raise ValueError('Duplicate frame instance')
            ids.add(obj['id'])
            x1,y1,x2,y2 = obj['box']
            if not 0 <= x1 < x2 <= width or not 0 <= y1 < y2 <= height:
                raise ValueError('Invalid box in clip coordinates')
            if not 0 <= obj['confidence'] <= 1: raise ValueError('Invalid confidence')
            for contour in obj['mask_contours']:
                if len(contour) < 3 or any(not(0 <= x < width and 0 <= y < height) for x,y in contour):
                    raise ValueError('Invalid mask contour')
        for hand in frame['hands']:
            is_2d=result['schema_version'] in {'labprism-video-result/2','labprism-video-result/3'} and hand.get('depth_available') is False
            if len(hand['points']) != 21 or any(len(p)!=3 or any(not math.isfinite(v) for v in p[:2]) or (p[2] is not None if is_2d else not isinstance(p[2],(int,float)) or not math.isfinite(p[2])) for p in hand['points']):
                raise ValueError('Hand requires 21 finite xyz points')
            if is_2d and (len(hand.get('point_scores',[]))!=21 or any(not math.isfinite(s) for s in hand['point_scores'])):
                raise ValueError('2D hand requires 21 finite model scores')
        semantic=frame.get('semantic_map')
        if semantic:
            if (result['schema_version'] not in {'labprism-video-result/2','labprism-video-result/3'} or semantic['taxonomy']!='ADE20K-150'
                    or not re.fullmatch(r'semantic-[0-9]+\.png',semantic['file'])
                    or not re.fullmatch(r'[0-9a-f]{64}',semantic['sha256'])):
                raise ValueError('Invalid semantic map identity')
        labels=set()
        for region in frame.get('semantic_regions',[]):
            label=region['class_id']
            if not semantic or not isinstance(label,int) or not 0<=label<150 or label in labels or not 0<=region['mean_score']<=1:
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
        if result['schema_version']=='labprism-video-result/3':
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
    if result['schema_version']=='labprism-video-result/3':
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
