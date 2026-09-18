"""Receipt verification at the producer/consumer boundary."""
import hashlib
import json
from pathlib import Path
import shutil

from labprism.contracts import validate_result


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_run(directory):
    """Check the full stored run, including evidence and producer/model identities."""
    directory = Path(directory)
    receipt = json.loads((directory / 'receipt.json').read_text())
    required = {'result.json', 'clip.mp4', 'model-receipt.json', 'producer-receipt.json'}
    if receipt.get('schema_version') != 'labprism-inference-run/1' or not required <= receipt['files'].keys():
        raise ValueError('Incomplete inference receipt')
    for folder, members in [(directory, receipt['files']), (directory/'evidence', receipt.get('evidence', {}))]:
        if folder.is_symlink():
            raise ValueError('Run directory cannot be a symlink')
        for name, expected in members.items():
            path = folder / name
            if Path(name).name != name or path.is_symlink() or not path.is_file() or sha256(path) != expected:
                raise ValueError(f'Run member identity mismatch: {name}')
    result = validate_result(json.loads((directory/'result.json').read_text()))
    producer = json.loads((directory/'producer-receipt.json').read_text())
    source = dict(result['source'])
    clip_hash = source.pop('clip_sha256')
    if source != producer or clip_hash != receipt['files']['clip.mp4'] or clip_hash != producer['files']['clip.mp4']:
        raise ValueError('Producer/video/result identity mismatch')
    if receipt['source_sha256'] != source['source_sha256']:
        raise ValueError('Source identity mismatch')
    if receipt['model_receipt_sha256'] != receipt['files']['model-receipt.json']:
        raise ValueError('Model receipt identity mismatch')
    registry = json.loads((directory/'model-receipt.json').read_text())
    if any(model not in registry['models'] for model in result['models']):
        raise ValueError('Result models differ from received registry')
    return result


def verify_release(directory):
    """READY means the internal artifact hashes match, never algorithm approval."""
    directory = Path(directory).resolve()
    ready = json.loads((directory/'READY.json').read_text())
    if sha256(directory/'release.json') != ready['release_sha256']:
        raise ValueError('Release manifest mismatch')
    receipt = json.loads((directory/'release.json').read_text())
    for name, item in receipt['files'].items():
        path = directory/name
        if Path(name).is_absolute() or '..' in Path(name).parts or any(p.is_symlink() for p in [path, *path.parents]) or not path.resolve().is_relative_to(directory):
            raise ValueError('Unsafe release member')
        if not path.is_file() or path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
            raise ValueError(f'Release member mismatch: {name}')
    return receipt


def verify_media(directory):
    directory = Path(directory).resolve()
    receipt = json.loads((directory / 'receipt.json').read_text())
    if receipt['schema_version'] != 'annotation-workbench-demo-media/1':
        raise ValueError('Unsupported media receipt')
    if receipt['split'] not in {'train', 'val'}:
        raise ValueError('Final test and holdout sources cannot enter a development demo')
    if receipt['camera_role'] not in {'first_person', 'third_person'}:
        raise ValueError('A known camera role is required')
    if receipt['annotations_exported'] or receipt['dataset_ownership_transferred']:
        raise ValueError('This boundary only receives unlabelled demonstration media')
    if 'clip.mp4' not in receipt['files']:
        raise ValueError('Missing clip identity')
    for name, expected in receipt['files'].items():
        path = directory / name
        if Path(name).name != name or path.is_symlink() or not path.is_file():
            raise ValueError('Unsafe or missing receipt member')
        if sha256(path) != expected:
            raise ValueError(f'Hash mismatch: {name}')
    return receipt


def receive_media(source, destination):
    source, destination = Path(source), Path(destination)
    receipt = verify_media(source)
    destination.mkdir(parents=True, exist_ok=False)
    for name in [*receipt['files'], 'receipt.json']:
        shutil.copyfile(source / name, destination / name)
    verify_media(destination)
    (destination / 'consumer-receipt.json').write_text(json.dumps({
        'schema_version': 'labprism-media-receive/1', 'producer_receipt': str(source / 'receipt.json'),
        'producer_receipt_sha256': sha256(source / 'receipt.json'), 'consumer': 'LabPrism',
        'purpose': 'local_diagnostic_inference', 'public_release_authorized': False,
    }, ensure_ascii=False, indent=2) + '\n')
    return receipt
