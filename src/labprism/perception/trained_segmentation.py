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


def restore_mask_logits(logits, boxes, transform):
    """Restore continuous logits before thresholding, using the actual letterbox.

    Boxes are in native image pixels. Missing object pixels are not repaired;
    interpolation only avoids magnifying an already-binary prototype grid.
    """
    import torch
    import torch.nn.functional as F
    from ultralytics.utils.ops import crop_mask
    t=transform
    if logits.ndim!=3 or boxes.shape!=(len(logits),4):
        raise ValueError('Mask logits and native boxes must have matching instances')
    if not torch.isfinite(logits).all() or not torch.isfinite(boxes).all():
        raise ValueError('Nonfinite mask logits or boxes')
    if not len(logits):
        return torch.empty((0,t['height'],t['width']),dtype=torch.uint8,device=logits.device)
    # Bound temporary float masks while retaining only the final binary output.
    native=[]
    for start in range(0,len(logits),8):
        square=F.interpolate(logits[start:start+8,None].float(),(t['size'],t['size']),
                             mode='bilinear',align_corners=False)
        cropped=square[:,:,t['top']:t['top']+t['nh'],t['left']:t['left']+t['nw']]
        restored=F.interpolate(cropped,(t['height'],t['width']),mode='bilinear',align_corners=False)[:,0]
        native.append(crop_mask(restored,boxes[start:start+8]).gt(0).to(torch.uint8))
    return torch.cat(native)


class JointSegmenter:
    def __init__(self, checkpoint, expected_sha256, role, source_role, *, imgsz=640, mask_decode='native_logits'):
        if type(imgsz) is not int or not 320<=imgsz<=1280 or imgsz%32:
            raise ValueError('Input size must be a multiple of 32 between 320 and 1280')
        if mask_decode not in {'binary_grid','native_logits'}:
            raise ValueError('Unknown mask decoding policy')
        self.imgsz=imgsz;self.mask_decode=mask_decode
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
        image,t=letterbox_rgb(rgb,self.imgsz)
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
            grid=list(p['proto'].shape[-2:])
            coefficients=p['mask_coefficient'][0,:,keep].T
            if self.mask_decode=='binary_grid':
                masks=process_mask(p['proto'][0],coefficients,boxes[keep],(self.imgsz,self.imgsz))
            else:
                proto=p['proto'][0]
                logits=(coefficients@proto.float().flatten(1)).reshape(-1,*grid)
                native_boxes=boxes[keep].clone()
                native_boxes[:,[0,2]]=(native_boxes[:,[0,2]]-t['left'])*t['width']/t['nw']
                native_boxes[:,[1,3]]=(native_boxes[:,[1,3]]-t['top'])*t['height']/t['nh']
                native_boxes[:,[0,2]]=native_boxes[:,[0,2]].clamp(0,t['width'])
                native_boxes[:,[1,3]]=native_boxes[:,[1,3]].clamp(0,t['height'])
                masks=restore_mask_logits(logits,native_boxes,t)
            boxes=boxes[keep].cpu().numpy();scores=scores[keep].cpu().tolist();classes=classes[keep].cpu().tolist();masks=masks.cpu().numpy()
        objects=[]
        for box,score,cls,mask in zip(boxes,scores,classes,masks,strict=True):
            box[[0,2]]=(box[[0,2]]-t['left'])*t['width']/t['nw']
            box[[1,3]]=(box[[1,3]]-t['top'])*t['height']/t['nh']
            box[[0,2]]=np.clip(box[[0,2]],0,t['width']);box[[1,3]]=np.clip(box[[1,3]],0,t['height'])
            if box[2]-box[0]<.01 or box[3]-box[1]<.01:continue
            native=restore_mask(mask,t) if self.mask_decode=='binary_grid' else mask
            contours,_=cv2.findContours(native,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
            objects.append({'class_id':int(cls),'label':self.names[int(cls)],'confidence':float(score),
                'box':box.tolist(),'mask_contours':[c.reshape(-1,2).tolist() for c in contours if len(c)>=3],
                'mask_score':None,'track_id':None,'mask_pixels':int(native.sum()),'mask_grid_size':grid,
                'mask_decode':self.mask_decode})
        return objects
