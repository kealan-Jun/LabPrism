import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('preview_showcase', Path(__file__).parents[1] / 'scripts/preview_website.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


def bundle(tmp_path):
    root = tmp_path / 'media/website/stills'
    root.mkdir(parents=True)
    (root / 'showcase.json').write_text('{"scenes":[]}')
    digest = hashlib.sha256((root / 'showcase.json').read_bytes()).hexdigest()
    (root / 'receipt.json').write_text(json.dumps({'mode': 'real_verified_inference_stills', 'files': {'showcase.json': digest}}))
    (tmp_path / 'receipts').mkdir()
    (tmp_path / 'receipts/website-showcase.json').write_text(json.dumps({'snapshot': str(root), 'receipt_sha256': hashlib.sha256((root / 'receipt.json').read_bytes()).hexdigest()}))
    return root


def test_rejects_tampered_showcase_before_copy(tmp_path):
    root = bundle(tmp_path)
    (root / 'showcase.json').write_text('changed')
    with pytest.raises(ValueError, match='hash'):
        preview.prepare_showcase(tmp_path, tmp_path / 'preview')
    assert not (tmp_path / 'preview').exists()


def test_verified_showcase_copy_and_symlink_rejection(tmp_path):
    root = bundle(tmp_path)
    out = tmp_path / 'preview'
    preview.prepare_showcase(tmp_path, out)
    assert (out / 'showcase/showcase.json').read_bytes() == (root / 'showcase.json').read_bytes()
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'showcase').symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='Unsafe'):
        preview.prepare_showcase(tmp_path, other)
