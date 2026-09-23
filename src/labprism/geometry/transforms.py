"""Explicit pixel-center affine transforms; coordinates never infer metric depth."""
import numpy as np


def transform_points(points, matrix):
    points, matrix = np.asarray(points, dtype=float), np.asarray(matrix, dtype=float)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError('Transform must be finite and invertible')
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError('Expected finite xy points')
    homogeneous = np.c_[points, np.ones(len(points))] @ matrix.T
    if np.any(np.abs(homogeneous[:, 2]) < 1e-12):
        raise ValueError('Point maps to infinity')
    return homogeneous[:, :2] / homogeneous[:, 2:]


def rotation_matrix(width, height, quarter_turns):
    """np.rot90 pixel-center map, original image → rotated model image."""
    matrices = [np.eye(3), [[0,1,0],[-1,0,width-1],[0,0,1]],
                [[-1,0,width-1],[0,-1,height-1],[0,0,1]],
                [[0,-1,height-1],[1,0,0],[0,0,1]]]
    return np.asarray(matrices[quarter_turns % 4], dtype=float)


def map_time(pts, time_base, *, clip_origin_ms=0, source_start_ms=0,
             capture_origin_ms=None, global_origin_ms=None):
    from fractions import Fraction
    media_ms = float(pts * Fraction(time_base) * 1000)
    clip_ms = media_ms - clip_origin_ms
    return {'media_pts': pts, 'time_base': str(Fraction(time_base)),
            'media_ms': media_ms, 'clip_ms': clip_ms,
            'source_ms': source_start_ms + clip_ms,
            'capture_ms': None if capture_origin_ms is None else capture_origin_ms + clip_ms,
            'global_ms': None if global_origin_ms is None else global_origin_ms + clip_ms}
