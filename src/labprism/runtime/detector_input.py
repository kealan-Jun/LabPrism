"""Receipted fresh-video sampling and exact replay share native frame identity."""
from contextlib import contextmanager
import hashlib
import math
from pathlib import Path

from labprism.artifacts import verify_run
from labprism.perception.trained_hand import verify_decoded_frame
from labprism.runtime.observation import verify_observation, validate_inference_source


@contextmanager
def detector_input(*, parent=None, media=None, sample_hz=5):
    import av

    if (parent is None) == (media is None):
        raise ValueError('Choose exactly one parent run or fresh media receipt')
    if not math.isfinite(sample_hz) or not 1 <= sample_hz <= 10:
        raise ValueError('Sampling must be bounded to 1–10 Hz')
    directory = Path(parent if parent is not None else media)
    targets = None
    if parent is not None:
        metadata = verify_run(directory)
        validate_inference_source(metadata)
        targets = {frame['frame_index']: frame for frame in metadata['frames']}
    else:
        source = verify_observation(directory)
        if source['camera_role'] not in {'first_person', 'third_person'}:
            raise ValueError('A known camera role is required for the configured detector')
    with av.open(str(directory / 'clip.mp4')) as clip:
        stream = clip.streams.video[0]
        origin = float((stream.start_time or 0) * stream.time_base * 1000)
        dimensions = [stream.width, stream.height]
        if parent is None:
            duration = float(stream.duration * stream.time_base * 1000) if stream.duration else source['duration_seconds'] * 1000
            statuses = {key: {'state': 'not_run', 'reason': 'Only detector inference requested'}
                        for key in ('boxes', 'instance_masks', 'semantic_map', 'keypoints', 'tracks', 'relations', 'events', 'readouts')}
            metadata = {
                'schema_version': 'labprism-video-result/4',
                'source': {**source, 'clip_sha256': source['files']['clip.mp4']},
                'video': {'file': 'clip.mp4', 'width': stream.width, 'height': stream.height,
                          'duration_ms': duration, 'sample_hz': sample_hz,
                          'coordinate_system': 'clip_pixels_top_left_xy', 'mirror_applied': False, 'rotation_applied': False},
                'data_use': {'purpose': 'production_observation' if source['split'] is None else 'development'},
                'semantic_taxonomy': {'id': 'not_run', 'version': '1', 'classes': [], 'unknown_id': None, 'ignore_id': None},
                'time_mapping': {'clip_origin_ms': origin, 'capture_origin_ms': None, 'global_origin_ms': None},
                'coordinates': {'clip_to_source': [[source['source_dimensions'][0] / stream.width, 0, 0],
                                                   [0, source['source_dimensions'][1] / stream.height, 0], [0, 0, 1]],
                                'operations': [] if dimensions == source['source_dimensions'] else
                                [{'type': 'producer_resize', 'source_dimensions': source['source_dimensions'], 'clip_dimensions': dimensions}]},
                'output_statuses': statuses,
            }
            validate_inference_source(metadata)
        elif dimensions != [metadata['video']['width'], metadata['video']['height']]:
            raise ValueError('Source decoder dimensions changed')

        def samples():
            next_ms, previous_ms = 0, -math.inf
            visited = set()
            for index, decoded in enumerate(clip.decode(stream)):
                if decoded.pts is None:
                    raise ValueError('Missing native video PTS')
                timestamp = round(float(decoded.pts * decoded.time_base * 1000) - origin, 6)
                if timestamp <= previous_ms:
                    raise ValueError('Video presentation timestamps are not increasing')
                previous_ms = timestamp
                if targets is not None:
                    if index not in targets:
                        continue
                else:
                    if timestamp < -.001 or timestamp + .001 < next_ms:
                        continue
                    next_ms = (int((timestamp + .001) * sample_hz / 1000) + 1) * 1000 / sample_hz
                rgb = decoded.to_ndarray(format='rgb24')
                if targets is not None:
                    frame = targets[index]
                    verify_decoded_frame(frame, rgb, decoded.pts, decoded.time_base, dimensions)
                else:
                    frame = {'frame_index': index, 'timestamp_ms': timestamp, 'presentation_seconds': timestamp / 1000,
                             'source_timestamp_ms': source['parent_start_seconds'] * 1000 + timestamp,
                             'clip_pts': decoded.pts, 'time_base': str(decoded.time_base),
                             'rgb_sha256': hashlib.sha256(rgb.tobytes()).hexdigest()}
                visited.add(index)
                yield frame, rgb[:, :, ::-1].copy()
            if not visited or (targets is not None and visited != targets.keys()):
                raise ValueError('Incomplete or empty sampled video')

        yield metadata, samples()
