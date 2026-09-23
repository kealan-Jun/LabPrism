import copy
import json
from pathlib import Path

import pytest

from labprism.artifacts import sha256
from labprism.runtime.observation import seal_observation, verify_observation
from labprism.runtime.jobs import Jobs


@pytest.fixture
def media(tmp_path, monkeypatch):
    directory = tmp_path / "observations" / "new-video"
    directory.mkdir(parents=True)
    (directory / "clip.mp4").write_bytes(b"unit test media")
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
        ],
        "format": {"duration": "12.5", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    }
    monkeypatch.setattr(
        "labprism.runtime.observation.subprocess.check_output",
        lambda *a, **kw: json.dumps(probe),
    )
    return (
        directory,
        probe,
        {"title": "test", "camera_id": "camera-A", "camera_role": "third_person"},
    )


def test_observation_retains_unknown_split_and_has_no_training_authorization(media):
    directory, _, metadata = media
    metadata["camera_role"] = "unknown"
    receipt = seal_observation(directory, metadata)
    assert receipt["split"] is None and receipt["camera_role"] == "unknown"
    assert receipt["training_use_authorized"] is False
    assert verify_observation(directory) == receipt
    with pytest.raises(FileExistsError):
        seal_observation(directory, metadata)
    (directory / "clip.mp4").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        verify_observation(directory)


@pytest.mark.parametrize(
    "change", ["rotation", "too_long", "nan", "too_large", "codec", "role"]
)
def test_intake_rejects_unrepresentable_media(media, change):
    directory, probe, metadata = media
    if change == "rotation":
        probe["streams"][0]["side_data_list"] = [{"rotation": 90}]
    if change == "too_long":
        probe["format"]["duration"] = 1801
    if change == "nan":
        probe["format"]["duration"] = "nan"
    if change == "too_large":
        probe["streams"][0]["width"] = 8192
    if change == "codec":
        probe["streams"][0]["codec_name"] = "hevc"
    if change == "role":
        metadata["camera_role"] = "camera-A"
    with pytest.raises(ValueError):
        seal_observation(directory, metadata)
    assert not (directory / "receipt.json").exists()


def test_restart_marks_interrupted_and_retry_preserves_original(
    media, monkeypatch, tmp_path
):
    directory, _, metadata = media
    seal_observation(directory, metadata)
    recipe = tmp_path / "recipe.json"
    recipe.write_text("{}")
    monkeypatch.setattr(
        Jobs, "settings", lambda self: {"recipe": str(recipe), "python": "/test/python"}
    )
    jobs = Jobs(tmp_path, Path.cwd(), lambda item: None, start_worker=False)
    identifier = jobs.submit(directory.name)["id"]
    original = copy.deepcopy(jobs.items[identifier])
    recovered = Jobs(tmp_path, Path.cwd(), lambda item: None, start_worker=False)
    assert recovered.items[identifier]["state"] == "failed"
    next_id = recovered.retry(identifier)["id"]
    assert next_id != identifier
    assert recovered.items[identifier]["recipe_sha256"] == original["recipe_sha256"]
    assert recovered.items[next_id]["retry_of"] == identifier
    assert recovered.items[next_id]["state"] == "queued"
    with pytest.raises(ValueError):
        recovered.submit("../outside")
    with pytest.raises(ValueError):
        recovered.retry(next_id)


def test_model_and_receipt_identity_fail_closed(tmp_path):
    from labprism.perception.display_video import load_recipe

    weight, receipt, producer, selector = [
        tmp_path / n
        for n in [
            "candidate.pt",
            "receipt.json",
            "producer-receipt.json",
            "selector.py",
        ]
    ]
    weight.write_bytes(b"weight")
    producer.write_text("{}")
    selector.write_text("source")
    receipt.write_text(
        json.dumps(
            {
                "weights_sha256": sha256(weight),
                "project_id": "instrument-display-surface-v2",
                "role": "first_person",
                "production_replacement": False,
                "producer_receipt_sha256": sha256(producer),
            }
        )
    )
    recipe = {
        "schema_version": "labprism-display-video-recipe/1",
        "sample_hz": 10,
        "model": {
            "path": str(weight),
            "sha256": sha256(weight),
            "receipt": str(receipt),
            "receipt_sha256": sha256(receipt),
            "role": "first_person",
        },
        "selection": {"path": str(selector), "sha256": sha256(selector)},
    }
    config = tmp_path / "recipe.json"
    config.write_text(json.dumps(recipe))
    assert load_recipe(config) == recipe
    producer.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="Producer"):
        load_recipe(config)
