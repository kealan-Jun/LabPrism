"""Causal image-supported association. No interpolated observations are emitted."""
from dataclasses import dataclass, field
import math

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .association import overlap


def descriptor(image, box):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = np.rint(box).astype(int)
    crop = image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        raise ValueError('Empty appearance crop')
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).ravel()
    # Also preserve brightness for low-saturation laboratory objects.
    value = cv2.calcHist([hsv], [2], None, [16], [0, 256]).ravel()
    return np.r_[hist / max(hist.sum(), 1), value / max(value.sum(), 1)] / 2


def appearance_distance(a, b):
    return float(np.sqrt(max(0., 1. - np.sqrt(a * b).sum())))


class CameraMotion:
    """Estimate global translation/rotation from consecutive background features."""
    def __init__(self):
        self.previous = None

    def update(self, image, objects):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=.5, fy=.5)
        previous, self.previous = self.previous, gray
        identity = np.array([[1., 0., 0.], [0., 1., 0.]])
        if previous is None or previous.shape != gray.shape:
            return identity, {'status':'unavailable', 'inliers':0}
        mask = np.full(previous.shape, 255, np.uint8)
        for obj in objects:
            x1, y1, x2, y2 = (np.array(obj['box']) / 2).astype(int)
            mask[max(y1, 0):y2, max(x1, 0):x2] = 0
        points = cv2.goodFeaturesToTrack(previous, 300, .01, 7, mask=mask)
        if points is None or len(points) < 12:
            return identity, {'status':'insufficient_features', 'inliers':0}
        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, gray, points, None)
        good = status.ravel().astype(bool) & np.isfinite(moved).all(axis=(1, 2))
        if good.sum() < 12:
            return identity, {'status':'insufficient_matches', 'inliers':0}
        matrix, inliers = cv2.estimateAffinePartial2D(points[good], moved[good], method=cv2.RANSAC,
                                                    ransacReprojThreshold=2, maxIters=1000)
        count = int(inliers.sum()) if inliers is not None else 0
        if matrix is None or count < 12 or count / good.sum() < .5:
            return identity, {'status':'rejected_fit', 'inliers':count}
        scale = math.hypot(matrix[0, 0], matrix[1, 0])
        if not .9 <= scale <= 1.1 or abs(matrix[0, 1]) > .15:
            return identity, {'status':'rejected_transform', 'inliers':count}
        matrix[:, 2] *= 2
        return matrix, {'status':'estimated', 'inliers':count, 'affine':matrix.round(6).tolist()}


@dataclass
class VisualTrack:
    id: str
    label: str
    box: np.ndarray
    appearance: np.ndarray
    time: float
    trail: list = field(default_factory=list)


class AppearanceTracker:
    def __init__(self, prefix='visual', max_gap_ms=2000, sample_interval_ms=100):
        self.prefix = prefix
        self.max_gap_ms = max_gap_ms
        self.sample_interval_ms = sample_interval_ms
        self.tracks = {}
        self.next_id = 0
        self.last_time = -math.inf

    def update(self, objects, timestamp_ms, image, camera_affine=None):
        if not math.isfinite(timestamp_ms) or timestamp_ms <= self.last_time:
            raise ValueError('Tracking requires increasing finite timestamps')
        self.last_time = timestamp_ms
        self.tracks = {k:t for k,t in self.tracks.items() if timestamp_ms-t.time <= self.max_gap_ms}
        old = list(self.tracks.values())
        if camera_affine is not None:
            for track in old:
                x1, y1, x2, y2 = track.box
                corners = np.array([[x1,y1,1],[x2,y1,1],[x2,y2,1],[x1,y2,1]]) @ camera_affine.T
                track.box = np.r_[corners.min(axis=0), corners.max(axis=0)]
        descriptions = [descriptor(image, o['box']) for o in objects]
        costs = np.full((len(old), len(objects)), 1e6)
        for i, track in enumerate(old):
            for j, obj in enumerate(objects):
                if track.label != obj['label']:
                    continue
                box = np.array(obj['box'])
                similarity = overlap(track.box, box)
                distance = appearance_distance(track.appearance, descriptions[j])
                displacement = np.linalg.norm((box[:2]+box[2:]-track.box[:2]-track.box[2:])/2)
                scale = max(np.linalg.norm(track.box[2:]-track.box[:2]), 1)
                area_ratio = np.prod(box[2:]-box[:2]) / max(np.prod(track.box[2:]-track.box[:2]), 1)
                # Appearance alone must not join remote objects with the same color.
                if not .35 <= area_ratio <= 2.85 or distance > .65:
                    continue
                if similarity >= .1 or (distance < .3 and displacement/scale < .8):
                    costs[i,j] = .55*(1-similarity) + .35*distance + .1*min(displacement/scale,1)
        assigned = {}
        if old and objects:
            for i,j in zip(*linear_sum_assignment(costs)):
                if costs[i,j] < .78:
                    assigned[j] = old[i]
        for j,obj in enumerate(objects):
            box = np.array(obj['box'], dtype=float)
            center = (box[:2]+box[2:])/2
            track = assigned.get(j)
            if track is None:
                self.next_id += 1
                track = VisualTrack(f'{self.prefix}-{self.next_id}', obj['label'], box, descriptions[j], timestamp_ms)
                self.tracks[track.id] = track
                obj['track_state'], obj['track_gap_ms'] = 'new', 0
            else:
                gap = timestamp_ms-track.time
                obj['track_state'] = 'reassociated_after_gap' if gap > self.sample_interval_ms*1.6 else 'associated'
                obj['track_gap_ms'] = gap
                track.appearance = .8*track.appearance + .2*descriptions[j]
            track.box, track.time = box, timestamp_ms
            track.trail.append([timestamp_ms, round(float(center[0]),2), round(float(center[1]),2)])
            track.trail = [p for p in track.trail if timestamp_ms-p[0] <= 2000]
            obj['track_id'], obj['trail'] = track.id, [list(p) for p in track.trail]
        return objects
