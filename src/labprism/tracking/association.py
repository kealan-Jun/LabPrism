"""Causal, per-camera association; tracks never manufacture detections during gaps."""
from dataclasses import dataclass, field
import math


def overlap(a, b):
    area = max(0, min(a[2],b[2])-max(a[0],b[0])) * max(0,min(a[3],b[3])-max(a[1],b[1]))
    aa = (a[2]-a[0])*(a[3]-a[1]); bb = (b[2]-b[0])*(b[3]-b[1])
    return area / max(aa+bb-area,1e-9)


def deduplicate_hands(objects, threshold=.5):
    kept=[]
    for obj in sorted((o for o in objects if o['label'] in {'hand','gloved_hand'}),key=lambda o:-o['confidence']):
        if all(overlap(obj['box'],other['box']) < threshold for other in kept):kept.append(obj)
    return kept


def reject_screen_conflicts(objects, context, containment=.8, confidence=.5):
    """Retain conflicting proposals in an explicit rejection record, never as GT."""
    kept,rejected=[],[]
    for obj in objects:
        conflicts=[]
        if obj['label']=='balance':
            a=obj['box'];area=(a[2]-a[0])*(a[3]-a[1])
            for candidate in context:
                b=candidate['box']
                intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                if candidate['label']=='laptop' and candidate['confidence']>=confidence and intersection/area>=containment:
                    conflicts.append(candidate)
        if conflicts:rejected.append(dict(obj,rejection={'reason':'conflicting_laptop_model_prediction','evidence':conflicts,'is_ground_truth':False}))
        else:kept.append(obj)
    return kept,rejected


@dataclass
class Track:
    id: str
    label: str
    box: list
    time: float
    velocity: tuple=(0.,0.)
    trail: list=field(default_factory=list)


class Tracker:
    def __init__(self, prefix='object', max_gap_ms=600, min_iou=.15):
        self.prefix=prefix;self.max_gap_ms=max_gap_ms;self.min_iou=min_iou
        self.tracks={};self.next_id=0;self.last_time=-math.inf

    def update(self, objects, timestamp_ms):
        from scipy.optimize import linear_sum_assignment
        import numpy as np
        if not math.isfinite(timestamp_ms) or timestamp_ms<=self.last_time:raise ValueError('Tracking requires increasing finite timestamps')
        self.last_time=timestamp_ms
        self.tracks={k:v for k,v in self.tracks.items() if timestamp_ms-v.time<=self.max_gap_ms}
        old=list(self.tracks.values());cost=np.full((len(old),len(objects)),1e6)
        for i,t in enumerate(old):
            dt=(timestamp_ms-t.time)/1000
            predicted=[t.box[0]+dt*t.velocity[0],t.box[1]+dt*t.velocity[1],t.box[2]+dt*t.velocity[0],t.box[3]+dt*t.velocity[1]]
            for j,obj in enumerate(objects):
                if t.label!=obj['label']:continue
                affinity=max(overlap(predicted,obj['box']),overlap(t.box,obj['box']))
                if affinity>=self.min_iou:cost[i,j]=1-affinity
        assigned={}
        if old and objects:
            for i,j in zip(*linear_sum_assignment(cost)):
                if cost[i,j]<1e6:assigned[j]=old[i]
        for j,obj in enumerate(objects):
            x,y,x2,y2=obj['box'];center=((x+x2)/2,(y+y2)/2)
            track=assigned.get(j)
            if track:
                gap=timestamp_ms-track.time;dt=gap/1000
                old_center=((track.box[0]+track.box[2])/2,(track.box[1]+track.box[3])/2)
                track.velocity=tuple(.5*prev+.5*(new-old)/dt for prev,new,old in zip(track.velocity,center,old_center))
                obj['track_state']='reassociated_after_gap' if gap>150 else 'associated'
                obj['track_gap_ms']=gap
            else:
                self.next_id+=1;track=Track(f'{self.prefix}-{self.next_id}',obj['label'],obj['box'],timestamp_ms)
                self.tracks[track.id]=track;obj['track_state']='new';obj['track_gap_ms']=0
            track.box=list(obj['box']);track.time=timestamp_ms
            track.trail.append([timestamp_ms,round(center[0],2),round(center[1],2)])
            track.trail=[p for p in track.trail if timestamp_ms-p[0]<=2000]
            obj['track_id']=track.id;obj['trail']=[list(p) for p in track.trail]
        return objects
