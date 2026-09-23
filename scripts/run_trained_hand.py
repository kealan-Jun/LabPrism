#!/usr/bin/env python3
"""Replay a receipted role-specific hand model on all verified parent frames."""

import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from labprism.artifacts import sha256, verify_run, freeze_sources
from labprism.contracts import validate_result
from labprism.perception.baseline import source_revision
from labprism.perception.hand_color import load_color_aligned_pose
from labprism.perception.hand_rotation import infer_orientations
from labprism.perception.trained_hand import (
    load_replay_model,
    verify_decoded_frame,
    hand_observations,
)
from labprism.tracking.association import deduplicate_hands
from labprism.understanding.proximity import relations_for_frame, build_events


def run(request_path, output):
    import av
    import cv2
    import numpy as np

    request = json.loads(request_path.read_text())
    parent_path = Path(request["parent"]["path"])
    for name in ("result", "receipt"):
        if (
            sha256(parent_path / (name + ".json"))
            != request["parent"][name + "_sha256"]
        ):
            raise ValueError("Frozen parent run changed")
    parent = verify_run(parent_path)
    model = load_replay_model(request, parent)
    tracking_ran = any(
        frame.get("availability", {}).get("tracking") != "not_run"
        for frame in parent["frames"]
    )
    cv2.setNumThreads(2)
    pose, color = load_color_aligned_pose(
        model, request["pipeline"]["path"], request["pipeline"]["sha256"],
        runtime=request.get("runtime"),
    )
    output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    source_root = Path(os.environ.get(
        "LABPRISM_DATA_ROOT", str(Path.home() / ".local/share/labprism")
    )) / "source-snapshots"
    source_root.mkdir(parents=True, exist_ok=True)
    source_archive = source_root / (
        "trained-hand-" + sha256(request_path) + "-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".zip"
    )
    implementation = freeze_sources(
        repo,
        [Path(__file__), *sorted((repo / "src/labprism").rglob("*.py"))],
        source_archive,
    )

    def write(name, value):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        )

    write("replay-request.json", request)
    write(
        "replay-protocol.json",
        {
            "request_sha256": sha256(request_path),
            "implementation": implementation,
            "local_source_archive": str(source_archive),
            "local_source_archive_sha256": sha256(source_archive),
            "color": color,
            "selection": "Four orientations, median score; unchanged .3 score gate",
            "timing_scope": "decode + hand pose + eligible dependent 2D geometry; excludes detector and other prior stages",
            "promotion": "none",
            "independent_quality": None,
        },
    )
    parent_receipt = json.loads((parent_path / "receipt.json").read_text())
    exclude = {
        "result.json",
        "model-receipt.json",
        "baseline-result.json",
        "baseline-receipt.json",
    }
    for name in parent_receipt["files"]:
        if name in exclude or name.endswith("source-code.zip"):
            continue
        if (output / name).exists():
            raise ValueError(
                "Replay member would replace an existing artifact: " + name
            )
        shutil.copyfile(parent_path / name, output / name)
    if parent_receipt.get("evidence"):
        (output / "evidence").mkdir()
        for name in parent_receipt["evidence"]:
            shutil.copyfile(parent_path / "evidence" / name, output / "evidence" / name)
    for name in ("result.json", "receipt.json"):
        shutil.copyfile(parent_path / name, output / ("baseline-" + name))
    shutil.copyfile(
        request["producer_receipt"]["path"], output / "hand-training-receipt.json"
    )
    registry = json.loads((parent_path / "model-receipt.json").read_text())
    registry["models"].append(model)
    registry["hand_training_receipt_sha256"] = sha256(
        output / "hand-training-receipt.json"
    )
    write("model-receipt.json", registry)
    result = copy.deepcopy(parent)
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    result["derived_from"] = {
        "result_sha256": request["parent"]["result_sha256"],
        "receipt_sha256": request["parent"]["receipt_sha256"],
        "mode": "same_pixels_current_parent_objects_trained_hand_inference",
    }
    result["models"].append(model)
    result["configuration"]["trained_hand_replay"] = {
        "model_id": model["id"],
        "role": model["role"],
        "color": color,
        "pose_turns": [0, 1, 2, 3],
        "pose_selection": "score",
        "pose_threshold": 0.3,
        "producer_receipt_sha256": request["producer_receipt"]["sha256"],
        "object_tracking": "reused_from_verified_parent" if tracking_ran else "not_run_in_parent",
        "promotion": "none",
    }
    result["parent_environment"] = result["environment"]
    import onnxruntime as ort
    gpu = None
    if color["runtime"]["device"] == "cuda":
        import torch
        gpu = torch.cuda.get_device_name(color["runtime"]["device_id"])
    result["environment"] = {
        "python": sys.version.split()[0],
        "gpu": gpu,
        "inference_batch": 1,
        "actual_execution_providers": {"pose": "ONNXRuntime " + color["execution_provider"]},
        "runtime": color["runtime"],
        "onnxruntime_module": ort.__file__,
        "packages": {
            k: importlib.metadata.version(k)
            for k in ("av", "rtmlib", "numpy")
        },
        "reused_modules": ["detection", "segmentation_if_present"] + (
            ["object_tracking"] if tracking_ran else []),
    }
    result["environment"]["packages"]["onnxruntime"] = ort.__version__
    result["parent_metrics"] = result["metrics"]
    targets = {f["frame_index"]: f for f in result["frames"]}
    visited, pose_times, active_times = set(), [], []
    start = time.perf_counter()
    with av.open(str(parent_path / "clip.mp4")) as clip:
        for index, decoded in enumerate(clip.decode(video=0)):
            if index not in targets:
                continue
            frame = targets[index]
            rgb = decoded.to_ndarray(format="rgb24")
            verify_decoded_frame(
                frame,
                rgb,
                decoded.pts,
                decoded.time_base,
                (result["video"]["width"], result["video"]["height"]),
            )
            objects = deduplicate_hands(frame["objects"])
            tick = time.perf_counter()
            _, chosen = infer_orientations(
                pose, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [o["box"] for o in objects]
            )
            milliseconds = (time.perf_counter() - tick) * 1000
            pose_times.append(milliseconds)
            if objects:
                active_times.append(milliseconds)
            frame["baseline_hands"] = frame["hands"]
            frame["hands"], frame["rejected_hands"] = hand_observations(
                frame, objects, chosen, model["id"]
            )
            frame["availability"]["hands"] = (
                "predicted" if frame["hands"] else "no_detection"
            )
            relation_start = time.perf_counter()
            frame["relations"] = relations_for_frame(
                frame, result["configuration"].get("proximity_threshold_px", 15)
            ) if tracking_ran else []
            relation_ms = (time.perf_counter() - relation_start) * 1000
            frame["parent_latency_ms"] = frame.get("latency_ms", {})
            frame["latency_ms"] = {"hands": milliseconds, "relations": relation_ms}
            frame["parent_candidate_latency_ms"] = frame.get("candidate_latency_ms", {})
            frame["candidate_latency_ms"] = {"trained_hand_pose": milliseconds}
            visited.add(index)
            if len(visited) % 100 == 0:
                print(
                    json.dumps({"processed": len(visited), "total": len(targets)}),
                    flush=True,
                )
    if visited != set(targets):
        raise ValueError("Replay did not decode all parent analysis frames")
    result["events"] = build_events(
        result["frames"], max_gap_ms=1000 / result["video"]["sample_hz"] * 1.6
    )
    elapsed = time.perf_counter() - start
    for key, present in (
        ("keypoints", any(f["hands"] for f in targets.values())),
        ("relations", any(f["relations"] for f in targets.values())),
        ("events", bool(result["events"])),
    ):
        result.setdefault("output_statuses", {})[key] = {
            "state": ("not_run" if key != "keypoints" and not tracking_ran
                      else "predicted" if present else "no_detection"),
            "reason": ("Object tracking unavailable; dependent temporal geometry not run"
                       if key != "keypoints" and not tracking_ran else
                       "Actual receipted hand inference and dependent 2D geometry; quality unapproved"),
        }
    result["metrics"] = {
        "processed_frames": len(targets),
        "frames_with_hands": sum(bool(f["hands"]) for f in targets.values()),
        "hand_observations": sum(len(f["hands"]) for f in targets.values()),
        "proximity_events": len(result["events"]),
        "candidate_processing_seconds": elapsed,
        "candidate_processing_fps": len(targets) / elapsed,
        "timing_scope": "decode + pose + eligible dependent 2D geometry; excludes detector and other prior stages",
        "pose_p50_ms": float(np.median(pose_times)),
        "pose_p95_ms": float(np.percentile(pose_times, 95)),
        "frames_with_pose_rois": len(active_times),
        "active_pose_p50_ms": float(np.median(active_times)) if active_times else None,
        "active_pose_p95_ms": float(np.percentile(active_times, 95))
        if active_times
        else None,
        **{
            k: None
            for k in (
                "accuracy",
                "generalization",
                "temporal_quality",
                "npu_fps",
                "full_pipeline_fps",
                "sampled_pipeline_fps",
            )
        },
    }
    result["limitations"].append(
        "Role-specific producer training; development-only candidate. Pose recomputed on current boxes; dependent 2D events require available tracks. Contact, action and independent joint accuracy remain unverified."
    )
    validate_result(result)
    write("result.json", result)
    write(
        "receipt.json",
        {
            "schema_version": "labprism-inference-run/1",
            "source_sha256": result["source"]["source_sha256"],
            "model_receipt_sha256": sha256(output / "model-receipt.json"),
            "files": {p.name: sha256(p) for p in output.iterdir() if p.is_file()},
            "evidence": parent_receipt.get("evidence", {}),
            "source_revision": source_revision(repo),
            "promotion": "none",
            "actual_trained_hand_replay": True,
        },
    )
    verify_run(output)
    print(json.dumps({"output": str(output), "metrics": result["metrics"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.output)
