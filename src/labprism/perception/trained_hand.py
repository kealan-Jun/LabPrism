"""Role-bound producer artifact consumption and exact-frame hand replay."""

import copy
import hashlib
import json
from pathlib import Path

from labprism.artifacts import sha256
from labprism.perception.hand_head import validate_training_receipt
from labprism.perception.hand_rotation import accepted
from labprism.perception.hand_color import pose_runtime_options


def load_replay_model(request, parent):
    if request.get("schema_version") != "labprism-trained-hand-replay/1":
        raise ValueError("Explicit trained-hand replay request required")
    role = parent["source"]["camera_role"]
    if (
        parent.get("schema_version")
        not in {"labprism-video-result/3", "labprism-video-result/4"}
        or parent["source"]["split"] not in {"train", "val"}
        or role != request.get("role")
    ):
        raise ValueError("Replay requires matching known role and development source")
    for key in ("candidate", "producer_receipt", "pipeline"):
        item = request[key]
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError("Replay artifact changed: " + key)
    producer = json.loads(Path(request["producer_receipt"]["path"]).read_text())
    validate_training_receipt(
        producer,
        role=role,
        parent_sha256=request["parent_model_sha256"],
        labels_sha256=request["labels_sha256"],
    )
    if not any(
        m["sha256"] == producer["parent_onnx_sha256"]
        and m["task"] == "hand_landmarks_candidate"
        for m in parent["models"]
    ):
        raise ValueError("Replay is not derived from this pose model")
    model = copy.deepcopy(request["candidate"])
    runtime = pose_runtime_options(request.get("runtime"))
    if (
        model["sha256"] != producer["inference"]["sha256"]
        or model.get("role") != role
        or not isinstance(model.get("id"), str)
        or not model["id"].strip()
        or any(m["id"] == model["id"] for m in parent["models"])
        or model.get("deployment_approved") is not False
    ):
        raise ValueError("Candidate identity, role or approval mismatch")
    model.update(
        task="hand_landmarks_candidate",
        backend="ONNXRuntime " + (
            "CUDAExecutionProvider" if runtime["device"] == "cuda" else "CPUExecutionProvider"
        ),
        producer_receipt=request["producer_receipt"]["path"],
        producer_receipt_sha256=request["producer_receipt"]["sha256"],
        labels_sha256=producer["labels_sha256"],
        status="research_candidate_only",
        parent_sha256=producer["parent_onnx_sha256"],
        code_license="Apache-2.0 MMPose/rtmlib",
        weights_license="Project diagnostic derivative; upstream/data licenses retained; no public release approval",
    )
    return model


def verify_decoded_frame(frame, rgb, pts, time_base, dimensions):
    if (
        list(rgb.shape[:2][::-1]) != list(dimensions)
        or pts != frame["clip_pts"]
        or str(time_base) != frame["time_base"]
        or hashlib.sha256(rgb.tobytes()).hexdigest() != frame["rgb_sha256"]
    ):
        raise ValueError("Replay pixels, dimensions or PTS differ from parent")


def hand_observations(frame, objects, predictions, model_id):
    if len(objects) != len(predictions):
        raise ValueError("Pose output count differs from requested ROIs")
    hands, rejected = [], []
    for i, (obj, pred) in enumerate(zip(objects, predictions)):
        hand = {
            "id": f"f{frame['frame_index']}-trained-h{i}",
            "source_object_id": obj["id"],
            "model_id": model_id,
            "box": copy.deepcopy(obj["box"]),
            "points": [[x, y, None] for x, y in pred["points"]],
            "point_scores": pred["scores"],
            "keypoint_threshold": 0.3,
            "depth_available": False,
            "handedness_model_output": None,
            "handedness_score": None,
            "orientation_degrees": pred["turns"] * 90,
            "original_to_model_image": pred["original_to_model_image"],
            "observation_type": "current_frame_model_inference",
            "track_id": obj.get("track_id"),
            "tracking_source": "unchanged_parent_source_object",
        }
        for key in ("track_state", "track_gap_ms", "trail", "tracking_exclusion"):
            if key in obj:
                hand[key] = copy.deepcopy(obj[key])
        (hands if accepted(pred) else rejected).append(hand)
    return hands, rejected
