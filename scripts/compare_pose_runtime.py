#!/usr/bin/env python3
"""Qualify CPU/CUDA parity on a frozen producer-labelled development cohort."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from labprism.artifacts import sha256
from labprism.evaluation import match_localization
from labprism.perception.hand_color import load_color_aligned_pose
from labprism.perception.hand_head import load_diagnostic_inputs
from labprism.perception.hand_rotation import infer_orientations, accepted


def run(request_path, output):
    import cv2
    import numpy as np
    import onnxruntime as ort
    import torch
    request = json.loads(request_path.read_text())
    if request.get("schema_version") != "labprism-trained-hand-comparison/1":
        raise ValueError("Frozen trained-hand comparison request required")
    _, labels = load_diagnostic_inputs(request)
    baseline = Path(request["baseline"]["path"])
    if sha256(baseline / "protocol.json") != request["baseline"]["protocol_sha256"]:
        raise ValueError("Frozen ROI baseline changed")
    images = [r for r in labels["images"] if r["annotation"].get(
        "task_layers", {}).get("hand_pose", {}).get("hands")]
    if not 1 <= len(images) <= 100:
        raise ValueError("Bounded development cohort required")
    output.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    write("protocol.json", {
        "schema_version": "labprism-pose-runtime-comparison/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_sha256": sha256(request_path), "model": request["candidate"],
        "labels": request["labels"], "baseline": request["baseline"],
        "selection": "same frozen detector boxes, RGB, four rotations, score selection, .3 gate",
        "gate": "max point difference <= 1e-4 px; max score difference <= 1e-4; identical orientation and emitted/accepted decisions; no PCK slice regression",
        "PCK": "0.1 annotated box diagonal; all known points including missed hands",
        "independent_ground_truth": False, "weight_promotion": "none",
    })
    cv2.setNumThreads(2)
    torch.set_num_threads(2)
    poses, evidence = {}, {}
    for mode in ("cpu", "cuda"):
        poses[mode], evidence[mode] = load_color_aligned_pose(
            request["candidate"], request["pipeline"], request["pipeline_sha256"],
            runtime={"device": mode},
        )
    rows, timings, differences = [], [], []
    for image in images:
        name, source, annotation = image["id"], image["source"], image["annotation"]
        layer = annotation["task_layers"]["hand_pose"]
        if annotation["split"] not in {"train", "val"} or layer["status"] != "reviewed":
            raise ValueError("Only reviewed development labels are eligible")
        raw = json.loads((baseline / (name + ".json")).read_text())
        if sha256(image["managed_path"]) != source["sha256"] or raw["image_sha256"] != source["sha256"]:
            raise ValueError("Frozen source/ROI pixels changed")
        boxes = [o["box"] for o in raw["objects"]]
        bgr = cv2.imread(image["managed_path"])
        predictions = {}
        for mode, pose in poses.items():
            started = time.perf_counter()
            _, predictions[mode] = infer_orientations(pose, bgr, boxes)
            timings.append({"image_id": name, "mode": mode,
                            "milliseconds": (time.perf_counter() - started) * 1000})
        for cpu, gpu in zip(predictions["cpu"], predictions["cuda"], strict=True):
            differences.append({
                "image_id": name,
                "point_max_abs_px": float(np.max(np.abs(np.asarray(cpu["points"]) - gpu["points"]))),
                "score_max_abs": float(np.max(np.abs(np.asarray(cpu["scores"]) - gpu["scores"]))),
                "orientation_equal": cpu["turns"] == gpu["turns"],
                "acceptance_equal": accepted(cpu) == accepted(gpu),
                "emission_equal": bool(np.array_equal(np.asarray(cpu["scores"]) >= .3,
                                                        np.asarray(gpu["scores"]) >= .3)),
            })
        truth = layer["hands"]
        matches = match_localization([h["xyxy_px"] for h in truth], boxes)
        for index, hand in enumerate(truth):
            known = [i for i, p in enumerate(hand["points"]) if p[2] == 2]
            diagonal = np.linalg.norm(np.asarray(hand["xyxy_px"][2:]) - hand["xyxy_px"][:2])
            row = {"image_id": name, "hand_id": hand["id"], "split": annotation["split"],
                   "gloved": hand["gloved"], "known": len(known)}
            for mode in poses:
                pred = predictions[mode][matches[index]] if index in matches else None
                good = pred is not None and accepted(pred)
                row[mode] = sum(good and pred["scores"][i] >= .3 and
                    np.linalg.norm(np.asarray(pred["points"][i]) - hand["points"][i][:2]) <= .1 * diagonal
                    for i in known)
                row[mode] = int(row[mode])
            rows.append(row)
        write(name + ".json", {"image_sha256": source["sha256"], "boxes": boxes, **predictions})
    slices = {}
    for row in rows:
        key = row["split"] + ("/glove" if row["gloved"] else "/bare")
        summary = slices.setdefault(key, {"known": 0, "cpu": 0, "cuda": 0})
        for k in summary:
            summary[k] += row[k]
    parity = bool(differences) and all(
        d["point_max_abs_px"] <= 1e-4 and d["score_max_abs"] <= 1e-4
        and d["orientation_equal"] and d["acceptance_equal"] and d["emission_equal"]
        for d in differences
    )
    report = {
        "protocol_sha256": sha256(output / "protocol.json"),
        "images": len(images), "hands": len(rows),
        "overall": {k: sum(row[k] for row in rows) for k in ("known", "cpu", "cuda")},
        "slices": slices, "rows": rows, "differences": differences, "timings": timings,
        "runtime": evidence, "onnxruntime": ort.__version__, "ort_module": ort.__file__,
        "gpu": torch.cuda.get_device_name(0), "parity_passed": parity,
        "gate_passed": parity and all(s["cuda"] >= s["cpu"] for s in slices.values()),
        "weight_promotion": "none", "independent_quality": None,
    }
    write("report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"rows", "differences", "timings"}}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.output)
