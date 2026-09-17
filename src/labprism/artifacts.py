"""Receipt verification at the producer/consumer boundary."""
import hashlib
import json
from pathlib import Path
import shutil


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


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
