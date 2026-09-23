import pytest

from labprism.perception.hand_head import (
    validate_head_receipt,
    validate_training_receipt,
)


def receipt():
    return {
        "schema_version": "annotation-workbench-hand-head-result/1",
        "status": "completed",
        "task_type": "hand_pose",
        "role": "first_person",
        "parent_onnx_sha256": "parent",
        "labels_sha256": "labels",
        "automatic_promotion": False,
        "promotion": "none",
        "quality_hold_unchanged": True,
        "trainable_parameters": 262144,
        "trainable_tensors": ["head.cls_x.weight", "head.cls_y.weight"],
    }


def check(value, role="first_person"):
    validate_head_receipt(
        value, role=role, parent_sha256="parent", labels_sha256="labels"
    )


def test_hand_head_candidate_cannot_cross_camera_roles():
    check(receipt())
    with pytest.raises(ValueError):
        check(receipt(), role="third_person")


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "failed"),
        ("parent_onnx_sha256", "other"),
        ("labels_sha256", "stale"),
        ("automatic_promotion", True),
        ("quality_hold_unchanged", False),
        ("trainable_tensors", ["backbone"]),
    ],
)
def test_uncompleted_or_mismatched_head_receipts_fail_closed(key, value):
    data = receipt()
    data[key] = value
    with pytest.raises(ValueError):
        check(data)


@pytest.mark.parametrize(
    "change", [None, "nan_export", "statistics", "provider", "scope"]
)
def test_full_network_requires_its_own_verified_training_scope(change):
    data = receipt()
    data.update(
        schema_version="annotation-workbench-full-hand-result/1",
        training_scope="full_network_frozen_bn_statistics",
        batch_norm_statistics_unchanged=True,
        export_max_abs_error=1e-5,
        inference_provider=["CPUExecutionProvider"],
    )
    if change == "nan_export":
        data["export_max_abs_error"] = float("nan")
    if change == "statistics":
        data["batch_norm_statistics_unchanged"] = False
    if change == "provider":
        data["inference_provider"] = ["unknown"]
    if change == "scope":
        data["training_scope"] = "random_initialization"
    if change is None:
        validate_training_receipt(
            data, role="first_person", parent_sha256="parent", labels_sha256="labels"
        )
    else:
        with pytest.raises(ValueError):
            validate_training_receipt(
                data,
                role="first_person",
                parent_sha256="parent",
                labels_sha256="labels",
            )
    with pytest.raises(ValueError, match="Output-head-only"):
        check(data)
