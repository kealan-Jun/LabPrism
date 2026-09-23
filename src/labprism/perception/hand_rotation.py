"""RTMPose orientation candidate using current pixels only; no future smoothing."""
import numpy as np
from labprism.geometry.transforms import rotation_matrix, transform_points


def select_orientation(variants, box, selection='score'):
    if selection not in {'score','consensus'}:
        raise ValueError('Unknown orientation selection')
    fallback=max(variants,key=lambda p:p['selection_score'])
    if selection=='score':return fallback
    # Choose an actual current-image estimate, never mix in future pixels or GT.
    # A high score alone cannot establish consistency between transformed views.
    supported=[]
    diagonal=max(1.,float(np.linalg.norm(np.asarray(box[2:])-box[:2])))
    for i,hand in enumerate(variants):
        if not accepted(hand):continue
        errors=[]
        for j,other in enumerate(variants):
            if i==j or not accepted(other):continue
            common=(np.asarray(hand['scores'])>=.3)&(np.asarray(other['scores'])>=.3)
            if common.sum()<8:continue
            distances=np.linalg.norm(np.asarray(hand['points'])[common]-np.asarray(other['points'])[common],axis=1)
            errors.append(float(np.median(distances)/diagonal))
        if errors:supported.append((float(np.median(errors)),-hand['selection_score'],i))
    if not supported:return {**fallback,'selection_method':'score_fallback_no_consensus'}
    error,_,index=min(supported)
    return {**variants[index],'selection_method':'orientation_consensus','agreement_error':error}


def infer_orientations(pose, image, boxes, turns=(0,1,2,3), selection='score'):
    """Score-selected orientation, same detector ROIs and unchanged point gate.

    Scores are model scores, not calibrated probabilities or visibility labels.
    All orientations and the chosen input transform remain inspectable.
    """
    if not boxes:
        return [], []
    h, w = image.shape[:2]
    variants = []
    for turn in turns:
        matrix = rotation_matrix(w, h, turn)
        rotated = np.ascontiguousarray(np.rot90(image, turn))
        rh, rw = rotated.shape[:2]
        rois = []
        for x1,y1,x2,y2 in boxes:
            corners = transform_points([[x1,y1],[x2,y1],[x2,y2],[x1,y2]], matrix)
            rois.append([max(0,float(corners[:,0].min())), max(0,float(corners[:,1].min())),
                         min(rw,float(corners[:,0].max())), min(rh,float(corners[:,1].max()))])
        points, scores = pose(rotated, bboxes=rois)
        mapped = [transform_points(p, np.linalg.inv(matrix)) for p in points]
        variants.append([{'points':p.tolist(), 'scores':s.tolist(), 'turns':turn,
                          'original_to_model_image':matrix.tolist(),
                          'selection_score':float(np.median(s))}
                         for p,s in zip(mapped,scores)])
    chosen = [select_orientation([v[i] for v in variants],box,selection) for i,box in enumerate(boxes)]
    return variants[0], chosen


def accepted(hand, threshold=.3):
    scores = np.asarray(hand['scores'])
    return bool(np.isfinite(hand['points']).all() and np.isfinite(scores).all()
                and np.median(scores) >= threshold and (scores >= threshold).sum() >= 8)
