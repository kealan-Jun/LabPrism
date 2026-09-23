import copy
import pytest

from labprism.perception.pose_runtime_evaluation import compare_pose_backends


def runs():
    cpu = {
        "source": {"source_sha256": "source"}, "video": {"width": 100, "height": 80},
        "models": [{"sha256": "pose"}],
        "environment": {"actual_execution_providers": {"pose": "ONNXRuntime CPUExecutionProvider"}, "packages": {"rtmlib": "0.0.16"}},
        "configuration": {"trained_hand_replay": {"color": {"model_input_size": [256, 256]}}},
        "frames": [{"frame_index": 1, "clip_pts": 10, "rgb_sha256": "pixels",
                    "objects": [{"box": [0, 0, 50, 50]}], "relations": [],
                    "hands": [{"points": [[10., 20., None]] * 21, "point_scores": [.8] * 21,
                               "box": [0, 0, 50, 50], "orientation_degrees": 90}]}],
        "events": [], "metrics": {"candidate_processing_seconds": 10},
    }
    cuda = copy.deepcopy(cpu)
    cuda["environment"]["actual_execution_providers"]["pose"] = "ONNXRuntime CUDAExecutionProvider"
    cuda["metrics"]["candidate_processing_seconds"] = 2
    return cpu, cuda


def test_same_outputs_record_speed_separately_from_unmeasured_accuracy():
    cpu, cuda = runs()
    result = compare_pose_backends(cpu, cuda)
    assert result["gate_passed"] and result["processing_speedup"] == 5
    assert result["joint_accuracy"] is None and result["full_pipeline_fps"] is None


@pytest.mark.parametrize("bad", ["pixels", "objects", "weights", "provider", "frames"])
def test_changed_evaluation_conditions_fail_closed(bad):
    cpu, cuda = runs()
    if bad == "pixels": cuda["frames"][0]["rgb_sha256"] = "other"
    if bad == "objects": cuda["frames"][0]["objects"] = []
    if bad == "weights": cuda["models"][0]["sha256"] = "other"
    if bad == "provider": cuda["environment"] = cpu["environment"]
    if bad == "frames": cuda["frames"] = []
    with pytest.raises(ValueError):
        compare_pose_backends(cpu, cuda)


@pytest.mark.parametrize("bad", ["coordinates", "orientation", "gate", "count", "events"])
def test_output_regression_prevents_backend_acceptance(bad):
    cpu, cuda = runs()
    hand = cuda["frames"][0]["hands"][0]
    if bad == "coordinates": hand["points"][0] = [11., 20., None]
    if bad == "orientation": hand["orientation_degrees"] = 180
    if bad == "gate": hand["point_scores"][0] = .2
    if bad == "count": cuda["frames"][0]["hands"] = []
    if bad == "events": cuda["events"] = [{"unexplained": True}]
    assert not compare_pose_backends(cpu, cuda)["gate_passed"]


def test_single_simcc_bin_is_reported_separately_from_strict_parity():
    cpu, cuda = runs()
    step = 50 * 1.25 / 512
    cuda["frames"][0]["hands"][0]["points"][0] = [10 + step, 20., None]
    result = compare_pose_backends(cpu, cuda)
    assert not result["gate_passed"]
    assert result["consumer_resolution_gate_passed"]
    cuda["frames"][0]["hands"][0]["points"][0] = [10 + 2 * step, 20., None]
    assert not compare_pose_backends(cpu, cuda)["consumer_resolution_gate_passed"]


def test_consumer_resolution_cannot_be_assumed_for_another_decoder():
    cpu, cuda = runs()
    cuda["configuration"]["trained_hand_replay"]["color"]["model_input_size"] = [192, 256]
    result = compare_pose_backends(cpu, cuda)
    assert result["gate_passed"]
    assert not result["consumer_resolution_gate_passed"]
