import numpy as np
import pytest
import json
import sys
from types import SimpleNamespace

from labprism.artifacts import sha256
from labprism.perception.hand_color import ColorAlignedPose, load_color_aligned_pose
from labprism.perception.hand_color import _cuda_pose, pose_runtime_options


def test_swaps_native_channels_once_preserving_pixels_boxes_and_backend_geometry():
    image = np.array([[[11, 22, 99], [33, 44, 88]]], dtype=np.uint8)
    calls = []
    boxes = [[0, 0, 2, 1]]
    points, scores = np.zeros((1, 21, 2)), np.ones((1, 21))

    def backend(pixels, bboxes):
        calls.append((pixels.copy(), bboxes))
        assert pixels.flags.c_contiguous
        return points, scores

    actual = ColorAlignedPose(backend)(image, boxes)
    assert actual[0] is points and actual[1] is scores
    assert calls[0][0].tolist() == [[[99, 22, 11], [88, 44, 33]]]
    assert calls[0][1] is boxes
    assert image.tolist() == [[[11, 22, 99], [33, 44, 88]]]


def test_empty_rois_do_not_trigger_backend_full_image_fallback():
    def forbidden(*args, **kwargs):
        raise AssertionError("Must not infer the full image")

    points, scores = ColorAlignedPose(forbidden)(np.zeros((20, 20, 3), np.uint8), [])
    assert points.shape == (0, 21, 2) and scores.shape == (0, 21)


def test_luminance_uses_bgr_weights_and_copies_equal_channels_without_mutating_input():
    image = np.array([[[255, 0, 0], [0, 0, 255]]], dtype=np.uint8)
    original = image.copy()
    calls = []

    def backend(pixels, bboxes):
        calls.append(pixels)
        return None

    ColorAlignedPose(backend, "luminance_rgb")(image, [[0, 0, 2, 1]])
    assert calls[0].tolist() == [[[29, 29, 29], [76, 76, 76]]]
    assert np.array_equal(original, image)


def test_unsupported_color_variant_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        ColorAlignedPose(None, "automatic")


def test_loader_uses_actual_graph_and_decoder_geometry_not_stale_affine(
    tmp_path, monkeypatch
):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake model fixture")
    metadata = tmp_path / "pipeline.json"
    pipeline = {
        "pipeline": {
            "tasks": [
                {
                    "transforms": [
                        {
                            "type": "Normalize",
                            "to_rgb": True,
                            "mean": [123.675, 116.28, 103.53],
                            "std": [58.395, 57.12, 57.375],
                        },
                        {"type": "TopDownAffine", "image_size": [192, 256]},
                    ]
                },
                {
                    "component": "SimCCLabelDecode",
                    "params": {
                        "input_size": [256, 256],
                        "simcc_split_ratio": 2,
                        "use_dark": False,
                    },
                },
            ]
        }
    }
    metadata.write_text(json.dumps(pipeline))
    session = SimpleNamespace(
        get_inputs=lambda: [SimpleNamespace(shape=["batch", 3, 256, 256])],
        get_providers=lambda: ["CPUExecutionProvider"],
    )
    calls = []

    def constructor(path, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(session=session)

    monkeypatch.setitem(sys.modules, "rtmlib", SimpleNamespace(RTMPose=constructor))
    info = {"path": str(model), "sha256": sha256(model)}
    _, evidence = load_color_aligned_pose(info, metadata, sha256(metadata))
    assert calls[0]["model_input_size"] == (256, 256)
    assert evidence["sdk_affine_metadata"] == [[192, 256]]
    session.get_inputs = lambda: [SimpleNamespace(shape=["batch", 3, 256, 192])]
    with pytest.raises(ValueError, match="Actual ONNX shape"):
        load_color_aligned_pose(info, metadata, sha256(metadata))
    session.get_inputs = lambda: [SimpleNamespace(shape=["batch", 3, 256, 256])]
    session.get_providers = lambda: ["CUDAExecutionProvider"]
    with pytest.raises(ValueError, match="Unexpected hand execution provider"):
        load_color_aligned_pose(info, metadata, sha256(metadata))
    with pytest.raises(ValueError, match="changed"):
        load_color_aligned_pose(info, metadata, "0" * 64)
    pipeline["pipeline"]["tasks"][0]["transforms"][0]["to_rgb"] = False
    metadata.write_text(json.dumps(pipeline))
    with pytest.raises(ValueError, match="unique RGB normalization"):
        load_color_aligned_pose(info, metadata, sha256(metadata))


@pytest.mark.parametrize(
    "image",
    [np.zeros((2, 2)), np.zeros((2, 2, 4), np.uint8), np.zeros((2, 2, 3), np.float32)],
)
def test_wrong_color_boundary_fails_instead_of_double_normalizing(image):
    with pytest.raises(ValueError):
        ColorAlignedPose(lambda *a, **kw: None)(image, [[0, 0, 2, 2]])


@pytest.mark.parametrize("runtime", [
    {"device": "auto"}, {"device": "cuda", "device_id": True},
    {"device": "cuda", "device_id": -1},
    {"device": "cuda", "gpu_memory_limit_mb": 0},
    {"device": "cpu", "device_id": 0}, {"fallback": True}, "cuda",
])
def test_runtime_rejects_ambiguous_backend_or_resource_requests(runtime):
    with pytest.raises(ValueError):
        pose_runtime_options(runtime)


@pytest.mark.parametrize("failure", [None, "missing_gpu", "missing_provider", "fallback"])
def test_cuda_session_fails_closed_and_reuses_pose_geometry(monkeypatch, failure):
    class Pose:
        def __init__(self, *args, **kwargs):
            raise AssertionError("The upstream constructor would create an unrestricted session")

    calls = {}
    class Options:
        def add_session_config_entry(self, key, value):
            calls[key] = value

    session = SimpleNamespace(
        disable_fallback=lambda: calls.update(disabled=True),
        get_providers=lambda: ["CPUExecutionProvider"] if failure == "fallback"
        else ["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    def construct(path, **kwargs):
        calls.update(path=path, **kwargs)
        return session
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: failure != "missing_gpu", device_count=lambda: 1,
    )))
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        SessionOptions=Options, InferenceSession=construct,
        get_available_providers=lambda: ["CPUExecutionProvider"] if failure == "missing_provider"
        else ["CPUExecutionProvider", "CUDAExecutionProvider"],
    ))
    args = (Pose, "model.onnx", (256, 256), {"mean": [1, 2, 3], "std": [4, 5, 6]},
            pose_runtime_options({"device": "cuda"}))
    if failure:
        with pytest.raises(RuntimeError):
            _cuda_pose(*args)
    else:
        backend = _cuda_pose(*args)
        assert calls["session.disable_cpu_ep_fallback"] == "1"
        assert calls["disabled"] is True
        assert calls["providers"][0][1]["gpu_mem_limit"] == 1024 ** 3
        assert calls["providers"][0][1]["use_tf32"] == "0"
        assert backend.session is session and backend.model_input_size == (256, 256)
        assert backend.mean == (1, 2, 3) and backend.to_openpose is False
