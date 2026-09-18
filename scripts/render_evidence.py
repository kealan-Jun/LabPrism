#!/usr/bin/env python3
"""Render actual stored predictions at their exact decoded frame index."""
import argparse,json,hashlib,sys
from pathlib import Path
import av,cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from labprism.artifacts import verify_run
p=argparse.ArgumentParser();p.add_argument('run');p.add_argument('output');a=p.parse_args()
run,out=Path(a.run),Path(a.output);out.mkdir(parents=True,exist_ok=True)
d=verify_run(run)
frames=[min(d['frames'],key=lambda f:abs(f['timestamp_ms']-t)) for t in [0,4000]]
targets={f['frame_index']:f for f in frames}
edges=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]
with av.open(str(run/'clip.mp4')) as container:
 for i,f in enumerate(container.decode(video=0)):
  if i not in targets:continue
  record=targets[i]
  if hashlib.sha256(f.to_ndarray(format='rgb24').tobytes()).hexdigest()!=record['rgb_sha256']:
   raise ValueError('Decoded frame differs from prediction input')
  raw=f.to_ndarray(format='bgr24');overlay=raw.copy()
  for obj in record['objects']:
   color=(int((obj['class_id']*51)%160+90),220,int((obj['class_id']*33)%150+90))
   contours=[np.array(c,dtype=np.int32).reshape(-1,1,2) for c in obj['mask_contours']]
   cv2.drawContours(overlay,contours,-1,color,1)
   x,y,x2,y2=map(int,obj['box']);cv2.rectangle(overlay,(x,y),(x2,y2),color,1)
   cv2.putText(overlay,f"{obj['label']} {obj['confidence']:.2f}",(x,max(y-3,13)),cv2.FONT_HERSHEY_SIMPLEX,.35,color,1)
  for hand in record['hands']:
   pts=[tuple(map(round,p[:2])) for p in hand['points']]
   for a,b in edges:cv2.line(overlay,pts[a],pts[b],(80,255,255),2)
   for point in pts:cv2.circle(overlay,point,3,(80,255,255),-1)
  joined=np.concatenate([raw,overlay],axis=1)
  destination=out/f'{run.name}-{record["timestamp_ms"]:.0f}.jpg'
  if destination.exists():raise FileExistsError(destination)
  if not cv2.imwrite(str(destination),joined):raise OSError('Could not save evidence')
