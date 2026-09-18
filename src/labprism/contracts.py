"""Semantic checks supplement the versioned JSON result contract."""
import math
import re


def validate_result(result):
    if result['schema_version'] not in {'labprism-video-result/1','labprism-video-result/2'}:
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
            is_2d=result['schema_version']=='labprism-video-result/2' and hand.get('depth_available') is False
            if len(hand['points']) != 21 or any(len(p)!=3 or any(not math.isfinite(v) for v in p[:2]) or (p[2] is not None if is_2d else not isinstance(p[2],(int,float)) or not math.isfinite(p[2])) for p in hand['points']):
                raise ValueError('Hand requires 21 finite xyz points')
            if is_2d and (len(hand.get('point_scores',[]))!=21 or any(not math.isfinite(s) for s in hand['point_scores'])):
                raise ValueError('2D hand requires 21 finite model scores')
        semantic=frame.get('semantic_map')
        if semantic:
            if (result['schema_version']!='labprism-video-result/2' or semantic['taxonomy']!='ADE20K-150'
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
    if not result['frames']: raise ValueError('Empty analysis')
    return result
