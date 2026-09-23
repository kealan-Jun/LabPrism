"""Receipted, role-specific joint detection/mask inference for inspection."""
from pathlib import Path
import json

from labprism.artifacts import sha256


def letterbox_rgb(rgb, size=640):
    import numpy as np
    from PIL import Image
    h,w=rgb.shape[:2]
    nw,nh=round(w*size/max(w,h)),round(h*size/max(w,h))
    left,top=(size-nw)//2,(size-nh)//2
    canvas=Image.new('RGB',(size,size),(114,114,114))
    canvas.paste(Image.fromarray(rgb).resize((nw,nh),Image.Resampling.BILINEAR),(left,top))
    return np.asarray(canvas).copy(),dict(width=w,height=h,nw=nw,nh=nh,left=left,top=top,size=size)


def restore_mask(mask, transform):
    import cv2
    import numpy as np
    t=transform
    square=cv2.resize(mask.astype(np.uint8),(t['size'],t['size']),interpolation=cv2.INTER_NEAREST)
    cropped=square[t['top']:t['top']+t['nh'],t['left']:t['left']+t['nw']]
    return cv2.resize(cropped,(t['width'],t['height']),interpolation=cv2.INTER_NEAREST)


class JointSegmenter:
    def __init__(self, checkpoint, expected_sha256, role, source_role):
        if role not in {'first_person','third_person'} or role!=source_role:
            raise ValueError('Segmentation role must match the producer camera role')
        if sha256(checkpoint)!=expected_sha256:
            raise ValueError('Segmentation checkpoint hash mismatch')
        import torch
        from ultralytics import YOLO
        if not torch.cuda.is_available():raise RuntimeError('CUDA required; no CPU fallback')
        self.model=YOLO(str(checkpoint)).model.float().eval().cuda()
        self.head=self.model.model[-1]
        if type(self.head).__name__!='Segment26' or self.head.end2end:
            raise ValueError('Expected receipted YOLO26 one2many segmentation architecture')
        self.names=self.model.names

    def predict(self,rgb):
        import numpy as np
        import torch
        import cv2
        from torchvision.ops import nms
        from ultralytics.utils.tal import make_anchors,dist2bbox
        from ultralytics.utils.ops import process_mask
        image,t=letterbox_rgb(rgb)
        tensor=torch.from_numpy(image.transpose(2,0,1).copy()).unsqueeze(0).cuda().float()/255
        with torch.inference_mode():
            _,p=self.model(tensor)
            anchors,stride=make_anchors(p['feats'],self.head.stride,.5)
            distances=p['boxes'].permute(0,2,1)
            if self.head.reg_max>1:
                distances=distances.reshape(1,-1,4,self.head.reg_max).softmax(-1)@torch.arange(self.head.reg_max,device='cuda',dtype=distances.dtype)
            boxes=dist2bbox(distances,anchors,xywh=False)[0]*stride
            scores,classes=p['scores'][0].sigmoid().max(0)
            candidates=torch.where(scores>=.25)[0]
            keep=candidates[nms(boxes[candidates]+classes[candidates,None]*7680,scores[candidates],.55)[:300]]
            masks=process_mask(p['proto'][0],p['mask_coefficient'][0,:,keep].T,boxes[keep],(640,640))
            boxes=boxes[keep].cpu().numpy();scores=scores[keep].cpu().tolist();classes=classes[keep].cpu().tolist();masks=masks.cpu().numpy()
        objects=[]
        for box,score,cls,mask in zip(boxes,scores,classes,masks,strict=True):
            box[[0,2]]=(box[[0,2]]-t['left'])*t['width']/t['nw']
            box[[1,3]]=(box[[1,3]]-t['top'])*t['height']/t['nh']
            box[[0,2]]=np.clip(box[[0,2]],0,t['width']);box[[1,3]]=np.clip(box[[1,3]],0,t['height'])
            if box[2]-box[0]<.01 or box[3]-box[1]<.01:continue
            native=restore_mask(mask,t)
            contours,_=cv2.findContours(native,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
            objects.append({'class_id':int(cls),'label':self.names[int(cls)],'confidence':float(score),
                'box':box.tolist(),'mask_contours':[c.reshape(-1,2).tolist() for c in contours if len(c)>=3],
                'mask_score':None,'track_id':None,'mask_pixels':int(native.sum()),'mask_grid_size':[160,160]})
        return objects
