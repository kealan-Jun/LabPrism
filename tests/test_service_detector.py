import copy
from fractions import Fraction
import hashlib
import json
from unittest.mock import patch

import av
import numpy as np
import pytest

from labprism.runtime.detector_input import detector_input, validate_inference_source
from labprism.runtime.observation import seal_observation


@pytest.fixture
def media(tmp_path):
    folder = tmp_path / "media"
    folder.mkdir()
    # Real codec, irregular timestamps and a nonzero stream origin; no model output.
    with av.open(str(folder / "clip.mp4"), "w") as container:
        stream = container.add_stream("libx264", rate=10)
        stream.width, stream.height = 32, 24
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        stream.codec_context.time_base = Fraction(1, 1000)
        for i, timestamp in enumerate([2000, 2100, 2400, 2500, 2900]):
            frame = av.VideoFrame.from_ndarray(
                np.full((24, 32, 3), i * 30, np.uint8), format="rgb24"
            )
            frame.pts, frame.time_base = timestamp, Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    seal_observation(
        folder,
        {
            "title": "Codec fixture",
            "camera_id": "fixture-camera",
            "camera_role": "third_person",
        },
    )
    return folder


def test_fresh_video_native_time_and_sparse_sampling(media):
    with detector_input(media=media, sample_hz=5) as (metadata, samples):
        frames = list(samples)
    assert metadata["time_mapping"]["clip_origin_ms"] == 2000
    assert metadata["source"]["split"] is None
    assert metadata["data_use"]["purpose"] == "production_observation"
    assert metadata["source"]["training_use_authorized"] is False
    assert [f["timestamp_ms"] for f, _ in frames] == [0, 400, 900]
    assert [f["frame_index"] for f, _ in frames] == [0, 2, 4]
    for frame, bgr in frames:
        assert (
            frame["rgb_sha256"]
            == hashlib.sha256(bgr[:, :, ::-1].copy().tobytes()).hexdigest()
        )
        assert (
            float(Fraction(frame["time_base"]) * frame["clip_pts"] * 1000)
            == frame["timestamp_ms"] + 2000
        )


@pytest.mark.parametrize(
    "change", ["unknown", "changed_media", "test", "implicit_training"]
)
def test_invalid_fresh_media_is_rejected(media, change):
    receipt = json.loads((media / "receipt.json").read_text())
    if change == "unknown":
        receipt["camera_role"] = "unknown"
    if change == "changed_media":
        (media / "clip.mp4").write_bytes(b"corrupt")
    if change == "test":
        receipt["split"] = "test"
    if change == "implicit_training":
        receipt["training_use_authorized"] = True
    (media / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        with detector_input(media=media):
            pass


@pytest.mark.parametrize(
    "change",
    ["test", "evaluation", "unknown", "fake_producer", "training", "ground_truth"],
)
def test_replay_purpose_and_role_are_not_bypassed(media, change):
    with detector_input(media=media) as (metadata, _):
        value = copy.deepcopy(metadata)
    validate_inference_source(value)
    if change == "test":
        value["source"]["split"] = "test"
    if change == "evaluation":
        value["data_use"]["purpose"] = "evaluation"
        value["source"]["split"] = "val"
    if change == "unknown":
        value["source"]["camera_role"] = "unknown"
    if change == "fake_producer":
        value["source"]["schema_version"] = "unreceipted"
    if change == "training":
        value["source"]["training_use_authorized"] = True
    if change == "ground_truth":
        value["source"]["independent_ground_truth"] = True
    with pytest.raises(ValueError):
        validate_inference_source(value)


@pytest.mark.parametrize(
    "change", [None, "pixels", "pts", "timebase", "missing_frame", "dimensions"]
)
def test_replay_requires_exact_native_sample_identity(media, change):
    with detector_input(media=media) as (metadata, samples):
        frames = [{**f, "objects": [], "hands": []} for f, _ in samples]
    # Isolate decoder verification from artifact hashing, tested separately.
    if change == "pixels":
        frames[0]["rgb_sha256"] = "0" * 64
    if change == "pts":
        frames[0]["clip_pts"] += 1
    if change == "timebase":
        frames[0]["time_base"] = "1/999"
    if change == "missing_frame":
        frames.append({**frames[-1], "frame_index": 999})
    if change == "dimensions":
        metadata["video"]["width"] += 1
    metadata["frames"] = frames
    with patch("labprism.runtime.detector_input.verify_run", return_value=metadata):
        if change:
            with pytest.raises(ValueError):
                with detector_input(parent=media) as (_, samples):
                    list(samples)
        else:
            with detector_input(parent=media) as (_, samples):
                replay = list(samples)
            assert [f for f, _ in replay] == frames


@pytest.mark.parametrize("rate", [0, 11, float("nan"), float("inf")])
def test_sampling_rate_is_bounded_before_opening_media(media, rate):
    with pytest.raises(ValueError, match="Sampling"):
        with detector_input(media=media, sample_hz=rate):
            pass
