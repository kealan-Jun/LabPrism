"""Semantic checks supplement the versioned JSON result contract."""
import math


def validate_result(result):
    if result['schema_version'] != 'labprism-video-result/1':
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
            if len(hand['points']) != 21 or any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in hand['points']):
                raise ValueError('Hand requires 21 finite xyz points')
    if not result['frames']: raise ValueError('Empty analysis')
    return result
