"""Consume a producer-owned diagnostic without granting deployment approval."""

import json
from pathlib import Path

from labprism.artifacts import sha256


def validate_training_receipt(receipt, *, role, parent_sha256, labels_sha256):
    if (
        receipt.get("schema_version")
        not in {
            "annotation-workbench-hand-head-result/1",
            "annotation-workbench-full-hand-result/1",
            "annotation-workbench-expanded-hand-result/1",
        }
        or receipt.get("status") != "completed"
        or receipt.get("task_type") != "hand_pose"
        or role not in {"first_person", "third_person"}
        or receipt.get("role") != role
        or receipt.get("parent_onnx_sha256") != parent_sha256
        or receipt.get("labels_sha256") != labels_sha256
        or receipt.get("automatic_promotion") is not False
        or receipt.get("promotion") != "none"
        or receipt.get("quality_hold_unchanged") is not True
    ):
        raise ValueError("Incompatible or uncompleted producer hand-head diagnostic")
    if receipt["schema_version"] == "annotation-workbench-hand-head-result/1":
        if (
            receipt.get("trainable_tensors")
            != ["head.cls_x.weight", "head.cls_y.weight"]
            or receipt.get("trainable_parameters") != 262144
        ):
            raise ValueError("Unexpected output-head training scope")
    else:
        error = receipt.get("export_max_abs_error")
        if (
            receipt.get("training_scope") != "full_network_frozen_bn_statistics"
            or receipt.get("batch_norm_statistics_unchanged") is not True
            or type(error) not in {int, float}
            or not 0 <= error <= 1e-4
            or receipt.get("inference_provider") != ["CPUExecutionProvider"]
        ):
            raise ValueError("Unverified full-network inference artifact")
    if receipt["schema_version"] == "annotation-workbench-expanded-hand-result/1":
        roles = receipt.get("training_roles")
        if (
            not isinstance(roles, list)
            or role not in roles
            or any(r not in {"first_person", "third_person"} for r in roles)
            or receipt.get("truth_status")
            != "mixed_project_reviewed_and_explicit_teacher_proposals"
            or receipt.get("independent_ground_truth") is not False
            or receipt.get("dataset", {}).get("sha256") != labels_sha256
            or receipt.get("all_train_hands_covered_each_epoch") is not True
        ):
            raise ValueError("Expanded hand training must preserve proposal and role provenance")


def validate_head_receipt(receipt, **expected):
    if receipt.get("schema_version") != "annotation-workbench-hand-head-result/1":
        raise ValueError("Output-head-only receipt required")
    validate_training_receipt(receipt, **expected)


def load_diagnostic_inputs(request):
    def verified(item):
        path = Path(item["path"])
        if sha256(path) != item["sha256"]:
            raise ValueError("Frozen diagnostic input changed")
        return path

    receipt = json.loads(verified(request["producer_receipt"]).read_text())
    labels = json.loads(verified(request["labels"]).read_text())
    validate_training_receipt(
        receipt,
        role=request["role"],
        parent_sha256=request["parent"]["sha256"],
        labels_sha256=request["labels"]["sha256"],
    )
    verified(request["parent"])
    verified(request["candidate"])
    if receipt["inference"]["sha256"] != request["candidate"]["sha256"]:
        raise ValueError("Candidate is not the receipted inference artifact")
    if labels.get("schema_version") != "annotation-workbench-task-export/1":
        raise ValueError("Producer task export required")
    if labels["project"]["id"] != receipt["project_id"]:
        raise ValueError("Producer project mismatch")
    groups, pixels = {}, {}
    for row in labels["images"]:
        ann = row["annotation"]
        if ann["split"] not in {"train", "val"} or ann["role"] != request["role"]:
            raise ValueError("Role mismatch or sealed evaluation input")
        for seen, key in [
            (groups, row["source"]["source_group"]),
            (pixels, row["source"]["pixel_sha256"]),
        ]:
            if key in seen and seen[key] != ann["split"]:
                raise ValueError("Evaluation source crosses train and val")
            seen[key] = ann["split"]
    return receipt, labels
