"""Image-plane proximity intervals with explicit observations, never contact claims."""
import math


def point_box_distance(point, box):
    x,y = point[:2]
    return math.hypot(max(box[0]-x, 0, x-box[2]), max(box[1]-y, 0, y-box[3]))


def relations_for_frame(frame, threshold_px=15):
    relations = []
    for hand in frame['hands']:
        scores = hand.get('point_scores', [1.]*21)
        # Distal fingertips only; missing/low-confidence tips are not evidence.
        tips = [(i,hand['points'][i]) for i in (4,8,12,16,20)
                if scores[i] >= hand.get('keypoint_threshold', .3)]
        if not tips or not hand.get('track_id'):
            continue
        for obj in frame['objects']:
            if obj['label'] in {'hand','gloved_hand'} or not obj.get('track_id'):
                continue
            index, distance = min(((i,point_box_distance(p,obj['box'])) for i,p in tips),key=lambda x:x[1])
            if distance <= threshold_px:
                relations.append({'type':'hand_object_proximity_2d','hand_id':hand['id'],
                    'object_id':obj['id'],'hand_track_id':hand['track_id'],'object_track_id':obj['track_id'],
                    'keypoint_index':index,'distance_px':round(distance,3),'threshold_px':threshold_px,
                    'object_label':obj['label'],'object_display_name':obj.get('display_name',obj['label']),
                    'physical_contact':None,'status':'unreviewed_geometric_proposal'})
    return relations


def build_events(frames, max_gap_ms=250, min_duration_ms=600, min_observations=4):
    active, completed = {}, []
    def finish(key):
        event = active.pop(key)
        if event['end_ms']-event['start_ms'] >= min_duration_ms and len(event['evidence']) >= min_observations:
            event['id'] = f'proximity-{len(completed)+1}'
            completed.append(event)
    for frame in frames:
        t = frame['timestamp_ms']
        current = {(r['hand_track_id'],r['object_track_id']):r for r in frame.get('relations',[])}
        for key in list(active):
            if key not in current or t-active[key]['end_ms'] > max_gap_ms:
                finish(key)
        for key,relation in current.items():
            if key not in active:
                active[key] = {'type':'hand_object_proximity_2d','start_ms':t,'end_ms':t,
                    'label':f"手与{relation['object_display_name']}接近（二维候选）",
                    'hand_track_id':key[0],'object_track_id':key[1],
                    'status':'unreviewed_geometric_proposal','physical_contact':None,
                    'step':None,'evidence':[]}
            active[key]['end_ms'] = t
            active[key]['evidence'].append({'frame_index':frame['frame_index'],'timestamp_ms':t,
                'hand_id':relation['hand_id'],'object_id':relation['object_id'],
                'keypoint_index':relation['keypoint_index'],'distance_px':relation['distance_px']})
    for key in list(active):
        finish(key)
    return sorted(completed,key=lambda e:(e['start_ms'],e['id']))
