import copy
import hashlib
import json
from fractions import Fraction

import numpy as np
import pytest

from labprism.artifacts import sha256
from labprism.perception.trained_hand import (
    hand_observations,
    load_replay_model,
    verify_decoded_frame,
)


def inputs(tmp_path):
    def artifact(name, content):
        path = tmp_path / name
        path.write_text(content)
        return {"path": str(path), "sha256": sha256(path)}

    candidate = {
        **artifact("model", "weights"),
        "id": "trained",
        "role": "first_person",
        "deployment_approved": False,
    }
    producer = {
        "schema_version": "annotation-workbench-full-hand-result/1",
        "status": "completed",
        "task_type": "hand_pose",
        "role": "first_person",
        "parent_onnx_sha256": "parent",
        "labels_sha256": "labels",
        "automatic_promotion": False,
        "promotion": "none",
        "quality_hold_unchanged": True,
        "training_scope": "full_network_frozen_bn_statistics",
        "batch_norm_statistics_unchanged": True,
        "export_max_abs_error": 1e-5,
        "inference_provider": ["CPUExecutionProvider"],
        "inference": {"sha256": candidate["sha256"]},
    }
    request = {
        "schema_version": "labprism-trained-hand-replay/1",
        "role": "first_person",
        "candidate": candidate,
        "producer_receipt": artifact("receipt", json.dumps(producer)),
        "pipeline": artifact("pipeline", "metadata"),
        "parent_model_sha256": "parent",
        "labels_sha256": "labels",
    }
    parent = {
        "schema_version": "labprism-video-result/4",
        "source": {"camera_role": "first_person", "split": "val"},
        "models": [
            {"id": "base", "sha256": "parent", "task": "hand_landmarks_candidate"}
        ],
    }
    return request, parent


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "role",
        "sealed",
        "parent",
        "candidate",
        "weights",
        "labels",
        "duplicate_id",
    ],
)
def test_replay_model_identity_and_role_gate(tmp_path, bad):
    request, parent = inputs(tmp_path)
    if bad == "role":
        parent["source"]["camera_role"] = "third_person"
    elif bad == "sealed":
        parent["source"]["split"] = "test"
    elif bad == "parent":
        parent["models"][0]["sha256"] = "other"
    elif bad == "candidate":
        request["candidate"]["role"] = "third_person"
    elif bad == "weights":
        (tmp_path / "model").write_text("changed")
    elif bad == "labels":
        request["labels_sha256"] = "stale"
    elif bad == "duplicate_id":
        request["candidate"]["id"] = "base"
    if bad:
        with pytest.raises(ValueError):
            load_replay_model(request, parent)
    else:
        assert load_replay_model(request, parent)["role"] == "first_person"


@pytest.mark.parametrize("bad", [None, "pixels", "pts", "time_base", "shape"])
def test_replay_checks_exact_pixels_and_media_time(bad):
    rgb = np.zeros((8, 10, 3), dtype=np.uint8)
    frame = {
        "clip_pts": 30,
        "time_base": "1/30",
        "rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
    }
    pts, tb, size = 30, Fraction(1, 30), [10, 8]
    if bad == "pixels":
        rgb[0, 0] = 255
    if bad == "pts":
        pts = 31
    if bad == "time_base":
        tb = Fraction(1, 15)
    if bad == "shape":
        size = [8, 10]
    if bad:
        with pytest.raises(ValueError):
            verify_decoded_frame(frame, rgb, pts, tb, size)
    else:
        verify_decoded_frame(frame, rgb, pts, tb, size)


def test_pose_abstention_preserves_parent_tracking_and_never_invents_depth():
    obj = {
        "id": "o1",
        "box": [1, 1, 5, 5],
        "track_id": None,
        "tracking_exclusion": "ambiguous",
    }
    before = copy.deepcopy(obj)
    pred = {
        "points": [[2, 3]] * 21,
        "scores": [0.8] * 21,
        "turns": 1,
        "original_to_model_image": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    }
    hands, rejected = hand_observations({"frame_index": 10}, [obj], [pred], "candidate")
    assert not rejected and hands[0]["track_id"] is None
    assert all(p[2] is None for p in hands[0]["points"])
    assert obj == before
    pred["scores"] = [0.2] * 21
    hands, rejected = hand_observations({"frame_index": 10}, [obj], [pred], "candidate")
    assert not hands and len(rejected) == 1
    with pytest.raises(ValueError):
        hand_observations({"frame_index": 10}, [obj], [], "candidate")


def test_legacy_v3_with_exact_frame_lineage_can_use_the_same_model_gate(tmp_path):
    request, parent = inputs(tmp_path)
    parent["schema_version"] = "labprism-video-result/3"
    assert load_replay_model(request, parent)["id"] == "trained"
    parent["schema_version"] = "labprism-video-result/1"
    with pytest.raises(ValueError):
        load_replay_model(request, parent)


def test_cuda_replay_records_the_requested_backend_without_promoting_weights(tmp_path):
    request, parent = inputs(tmp_path)
    request["runtime"] = {"device": "cuda", "device_id": 0, "gpu_memory_limit_mb": 1024}
    model = load_replay_model(request, parent)
    assert model["backend"] == "ONNXRuntime CUDAExecutionProvider"
    assert model["deployment_approved"] is False
    assert model["sha256"] == request["candidate"]["sha256"]
    request["runtime"]["device"] = "auto"
    with pytest.raises(ValueError):
        load_replay_model(request, parent)
