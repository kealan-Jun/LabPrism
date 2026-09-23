"""Compare backend changes without treating CPU predictions as joint truth."""
import numpy as np


def compare_pose_backends(cpu, cuda):
    if cpu["source"] != cuda["source"] or cpu["video"] != cuda["video"]:
        raise ValueError("Backend comparison requires the same source and video")
    if cpu["models"][-1]["sha256"] != cuda["models"][-1]["sha256"]:
        raise ValueError("Backend comparison requires identical pose weights")
    if cpu["environment"]["actual_execution_providers"]["pose"] != "ONNXRuntime CPUExecutionProvider" or cuda["environment"]["actual_execution_providers"]["pose"] != "ONNXRuntime CUDAExecutionProvider":
        raise ValueError("Actual CPU and CUDA runs are required")
    maximum_point, maximum_score, hands = 0., 0., 0
    maximum_visible_px, maximum_visible_bins = 0., 0.
    resolution_contract = all(
        run.get("configuration", {}).get("trained_hand_replay", {}).get("color", {}).get("model_input_size") == [256, 256]
        and run["environment"].get("packages", {}).get("rtmlib") == "0.0.16"
        for run in (cpu, cuda)
    )
    if len(cpu["frames"]) != len(cuda["frames"]) or not cpu["frames"]:
        raise ValueError("Backend comparison requires the same nonempty frame cohort")
    changes = []
    for old, new in zip(cpu["frames"], cuda["frames"], strict=True):
        for key in ("frame_index", "clip_pts", "time_base", "rgb_sha256", "timestamp_ms",
                    "source_timestamp_ms", "objects", "texts", "semantic_map", "semantic_regions",
                    "temporal_instances", "camera_motion"):
            if old.get(key) != new.get(key):
                raise ValueError("Source or reused module changed: " + key)
        for layer in ("hands", "rejected_hands"):
            a, b = old.get(layer, []), new.get(layer, [])
            if len(a) != len(b):
                changes.append({"frame": old["frame_index"], "layer": layer, "reason": "count"})
                continue
            for left, right in zip(a, b, strict=True):
                hands += layer == "hands"
                keys = set(left) | set(right)
                for key in keys - {"points", "point_scores"}:
                    if left.get(key) != right.get(key):
                        changes.append({"frame": old["frame_index"], "layer": layer, "reason": key})
                p, q = np.asarray([v[:2] for v in left["points"]]), np.asarray([v[:2] for v in right["points"]])
                s, t = np.asarray(left["point_scores"]), np.asarray(right["point_scores"])
                if p.shape != q.shape or s.shape != t.shape or not all(np.isfinite(v).all() for v in (p,q,s,t)):
                    raise ValueError("Invalid pose tensors")
                maximum_point = max(maximum_point, float(np.max(np.abs(p-q))))
                maximum_score = max(maximum_score, float(np.max(np.abs(s-t))))
                if not np.array_equal(s >= .3, t >= .3):
                    changes.append({"frame": old["frame_index"], "layer": layer, "reason": "point_gate"})
                # This is separate from strict numeric parity. RTMPose's pinned
                # square 256 input uses 1.25 padded ROI and a 512-bin SimCC axis.
                # Only points actually consumed/displayed qualify for this bound.
                visible = (s >= .3) | (t >= .3)
                if layer == "hands" and visible.any() and "box" in left:
                    box = left["box"]
                    step = 1.25 * max(box[2]-box[0], box[3]-box[1]) / 512
                    if step <= 0:
                        raise ValueError("Invalid pose ROI")
                    delta = float(np.max(np.abs(p[visible]-q[visible])))
                    maximum_visible_px = max(maximum_visible_px, delta)
                    maximum_visible_bins = max(maximum_visible_bins, delta / step)
                elif layer == "hands" and visible.any():
                    maximum_visible_bins = float("inf")
    times = {"cpu": cpu["metrics"], "cuda": cuda["metrics"]}
    geometry_equal = all(a.get("relations") == b.get("relations") for a,b in zip(cpu["frames"], cuda["frames"])) and cpu["events"] == cuda["events"]
    return {
        "frames": len(cpu["frames"]), "accepted_hands": hands,
        "max_point_difference_px": maximum_point, "max_score_difference": maximum_score,
        "decision_changes": changes, "dependent_geometry_equal": geometry_equal,
        "gate_passed": not changes and maximum_point <= 1e-4 and maximum_score <= 1e-4 and geometry_equal,
        "max_visible_point_difference_px": maximum_visible_px,
        "max_visible_difference_simcc_bins": maximum_visible_bins,
        "consumer_resolution_contract_verified": resolution_contract,
        "consumer_resolution_gate_passed": resolution_contract and not changes and maximum_visible_bins <= 1.0001 and maximum_score <= 1e-4 and geometry_equal,
        "metrics": times,
        "processing_speedup": times["cpu"]["candidate_processing_seconds"] / times["cuda"]["candidate_processing_seconds"],
        "full_pipeline_fps": None, "joint_accuracy": None,
        "measurement_scope": "paired shared-host runs; decode + pose + dependent geometry; reused detection/masks/tracks excluded",
    }
