"""Local inference inputs are observations, never an implicit training dataset."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess

from labprism.artifacts import sha256, verify_media
from labprism.contracts import validate_v4_metadata


def seal_observation(directory, metadata):
    directory = Path(directory)
    clip = directory / 'clip.mp4'
    if (directory / 'receipt.json').exists():
        raise FileExistsError('Observation already sealed')
    if not isinstance(metadata, dict):
        raise ValueError('Invalid video metadata')
    role = metadata.get('camera_role', 'unknown')
    if role not in {'first_person', 'third_person', 'unknown'}:
        raise ValueError('Invalid camera role')
    for key in ('title', 'camera_id'):
        if not isinstance(metadata.get(key), str) or not 1 <= len(metadata[key].strip()) <= 160:
            raise ValueError(f'Invalid {key}')
    if clip.is_symlink() or not clip.is_file():
        raise ValueError('Missing local video')
    try:
        probe = json.loads(subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(clip)],
            timeout=30, stderr=subprocess.DEVNULL))
    except (subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise ValueError('无法读取视频，请确认文件完整并使用 H.264 MP4 格式') from error
    stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
    if (not stream or stream['codec_name'] != 'h264'
            or 'mp4' not in probe['format'].get('format_name', '').split(',')):
        raise ValueError('目前支持 H.264 MP4 视频，请先转换编码后重试')
    duration = float(probe['format'].get('duration', 0))
    width, height = stream['width'], stream['height']
    if not math.isfinite(duration) or not 0 < duration <= 1800 or not 1 <= width <= 4096 or not 1 <= height <= 4096:
        raise ValueError('视频须在 30 分钟内，分辨率不超过 4096 × 4096')
    # Rotation metadata changes browser presentation coordinates. Do not draw
    # decoded-pixel boxes on a silently rotated browser video.
    rotations = [float(stream.get('tags', {}).get('rotate', 0))]
    rotations.extend(float(s.get('rotation', 0)) for s in stream.get('side_data_list', []))
    if any(r % 360 for r in rotations):
        raise ValueError('请先将带旋转标记的视频转换为实际朝向的像素')
    digest = sha256(clip)
    receipt = dict(
        schema_version='labprism-local-observation/1', producer='LabPrism local intake',
        created_at=datetime.now(timezone.utc).isoformat(), source_id=f'local-{digest}',
        source_sha256=digest, files={'clip.mp4': digest}, title=metadata['title'].strip(),
        source_group=None, split=None, camera_id=metadata['camera_id'].strip(),
        camera_role=role, role_basis=metadata.get('role_basis', 'user_supplied'),
        source_dimensions=[width, height], parent_start_seconds=0,
        duration_seconds=duration, complete_source_file=True,
        experiment_completeness='unverified', baseline_exposure='unknown',
        provenance=metadata.get('provenance', {}), license='local product inspection only; not public release',
        public_release_authorized=False, annotations_exported=False,
        dataset_ownership_transferred=False, label_revision=None,
        independent_ground_truth=False, training_use_authorized=False)
    (directory / 'source-probe.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2))
    receipt['files']['source-probe.json'] = sha256(directory / 'source-probe.json')
    (directory / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


def verify_observation(directory):
    directory = Path(directory)
    receipt = json.loads((directory / 'receipt.json').read_text())
    if receipt.get('schema_version') == 'annotation-workbench-demo-media/1':
        return verify_media(directory)
    if (receipt.get('schema_version') != 'labprism-local-observation/1'
            or receipt.get('split') is not None or receipt.get('training_use_authorized') is not False
            or receipt.get('camera_role') not in {'first_person', 'third_person', 'unknown'}
            or receipt.get('files', {}).get('clip.mp4') != receipt.get('source_sha256')):
        raise ValueError('Invalid local observation receipt')
    for name, digest in receipt['files'].items():
        path = directory / name
        if Path(name).name != name or path.is_symlink() or not path.is_file() or sha256(path) != digest:
            raise ValueError('Observation member changed')
    return receipt


def validate_inference_source(result):
    """Inference does not assign unknown observations to a training split."""
    source = result['source']
    if source.get('camera_role') not in {'first_person', 'third_person'}:
        raise ValueError('A known camera role is required for the configured detector')
    if result.get('schema_version') == 'labprism-video-result/4':
        validate_v4_metadata(result)
        purpose = result['data_use']['purpose']
        if purpose == 'production_observation':
            if (source.get('schema_version') != 'labprism-local-observation/1'
                    or source.get('training_use_authorized') is not False
                    or source.get('independent_ground_truth') is not False):
                raise ValueError('Production observation requires its original non-training receipt')
            return
        if purpose != 'development':
            raise ValueError('This inference entry does not consume evaluation sources')
    if source.get('split') not in {'train', 'val'}:
        raise ValueError('Development inference cannot consume sealed tests')
