"""Explicit OpenCV BGR to model RGB boundary for the pinned RTMPose hand model."""

import json
from pathlib import Path

import numpy as np

from labprism.artifacts import sha256


class ColorAlignedPose:
    """Reuse the backend geometry/normalization; convert channels exactly once."""

    def __init__(self, backend, transform="rgb"):
        if transform not in {"rgb", "luminance_rgb"}:
            raise ValueError("Unsupported hand color transform")
        self.backend = backend
        self.transform = transform

    def __call__(self, image, bboxes):
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise ValueError("Hand pose expects native uint8 OpenCV BGR pixels")
        if not bboxes:
            return np.empty((0, 21, 2)), np.empty((0, 21))
        if self.transform == "luminance_rgb":
            import cv2

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            pixels = np.repeat(gray[:, :, None], 3, axis=2)
        else:
            pixels = np.ascontiguousarray(image[:, :, ::-1])
        return self.backend(pixels, bboxes=bboxes)


def pose_runtime_options(runtime=None):
    """An explicit CUDA request must never become an implicit CPU fallback."""
    runtime = {} if runtime is None else runtime
    if not isinstance(runtime, dict) or set(runtime) - {
        "device", "device_id", "gpu_memory_limit_mb"
    }:
        raise ValueError("Unsupported pose runtime configuration")
    device = runtime.get("device", "cpu")
    if device not in {"cpu", "cuda"}:
        raise ValueError("Pose device must be cpu or cuda")
    if device == "cpu":
        if set(runtime) - {"device"}:
            raise ValueError("GPU options require an explicit CUDA device")
        return {"device": device}
    index = runtime.get("device_id", 0)
    memory = runtime.get("gpu_memory_limit_mb", 1024)
    if type(index) is not int or index < 0 or type(memory) is not int or memory < 256:
        raise ValueError("Invalid CUDA device or memory budget")
    return {"device": device, "device_id": index, "gpu_memory_limit_mb": memory}


def _cuda_pose(pose_type, path, size, norm, runtime):
    # Reuse rtmlib's affine transform, normalization and SimCC decoding, as the
    # producer's CUDA pose worker does. Only session creation differs: rtmlib's
    # constructor does not expose memory limits or fail-closed provider options.
    import torch  # Load the existing CUDA 12 / cuDNN 9 libraries before ORT.
    import onnxruntime as ort

    index = runtime["device_id"]
    if not torch.cuda.is_available() or index >= torch.cuda.device_count():
        raise RuntimeError("Requested CUDA device is unavailable")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("ONNX Runtime has no CUDA provider; CPU fallback refused")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    session = ort.InferenceSession(
        str(path), sess_options=options,
        providers=[("CUDAExecutionProvider", {
            "device_id": index,
            "gpu_mem_limit": runtime["gpu_memory_limit_mb"] * 1024 * 1024,
            "cudnn_conv_algo_search": "HEURISTIC",
            "cudnn_conv_use_max_workspace": "0",
            "use_tf32": "0",
        })],
    )
    session.disable_fallback()
    providers = session.get_providers()
    # ORT registers its CPU provider automatically even when assignment to it
    # is disabled. The session config rejects CPU graph placement at creation;
    # registration alone does not mean an operator actually ran there.
    if not providers or providers[0] != "CUDAExecutionProvider" or set(providers) - {
        "CUDAExecutionProvider", "CPUExecutionProvider"
    }:
        raise RuntimeError("Unexpected CUDA pose providers; CPU fallback refused")
    backend = object.__new__(pose_type)
    backend.onnx_model = str(path)
    backend.session = session
    backend.model_input_size = size
    backend.mean, backend.std = tuple(norm["mean"]), tuple(norm["std"])
    backend.backend, backend.device = "onnxruntime", f"cuda:{index}"
    backend.to_openpose = False
    return backend


def load_color_aligned_pose(
    model, pipeline_path, pipeline_sha256, transform="rgb", *, runtime=None
):
    """Use hash-pinned SDK normalization and verify the actual ONNX input geometry.

    The historical SDK bundle has stale 192x256 affine metadata, but the actual
    graph and SimCC decoder are 256x256. Reject geometry disagreement with the
    decoder instead of changing the real model input to that stale affine size.
    """
    from rtmlib import RTMPose

    if (
        sha256(model["path"]) != model["sha256"]
        or sha256(pipeline_path) != pipeline_sha256
    ):
        raise ValueError("Pose weights or normalization metadata changed")
    pipeline = json.loads(Path(pipeline_path).read_text())["pipeline"]["tasks"]
    transforms = [t for task in pipeline for t in task.get("transforms", [])]
    norms = [t for t in transforms if t.get("type") == "Normalize"]
    decoders = [
        t["params"] for t in pipeline if t.get("component") == "SimCCLabelDecode"
    ]
    if len(norms) != 1 or len(decoders) != 1 or norms[0].get("to_rgb") is not True:
        raise ValueError("Explicit unique RGB normalization and SimCC decoder required")
    norm, decoder = norms[0], decoders[0]
    if (
        len(norm["mean"]) != 3
        or len(norm["std"]) != 3
        or not np.isfinite(norm["mean"]).all()
        or not np.isfinite(norm["std"]).all()
        or min(norm["std"]) <= 0
        or decoder.get("simcc_split_ratio") != 2
        or decoder.get("use_dark") is not False
    ):
        raise ValueError("Unsupported hand normalization or decoder")
    size = tuple(decoder["input_size"])
    if len(size) != 2 or any(type(v) is not int or not 16 <= v <= 2048 for v in size):
        raise ValueError("Invalid hand model input size")
    runtime = pose_runtime_options(runtime)
    provider = "CUDAExecutionProvider" if runtime["device"] == "cuda" else "CPUExecutionProvider"
    if runtime["device"] == "cuda":
        backend = _cuda_pose(RTMPose, model["path"], size, norm, runtime)
    else:
        backend = RTMPose(
            model["path"], model_input_size=size,
            mean=tuple(norm["mean"]), std=tuple(norm["std"]),
            backend="onnxruntime", device="cpu",
        )
    graph_size = backend.session.get_inputs()[0].shape
    if graph_size[1:] != [3, size[1], size[0]]:
        raise ValueError("Actual ONNX shape does not match decoder geometry")
    providers = backend.session.get_providers()
    if not providers or providers[0] != provider or (
        runtime["device"] == "cpu" and providers != [provider]
    ):
        raise ValueError("Unexpected hand execution provider")
    evidence = {
        "schema_version": "labprism-hand-color-contract/1",
        "input_pixels": "OpenCV BGR uint8",
        "model_channels": "RGB",
        "conversion_count": 1,
        "input_transform": transform,
        "model_input_size": list(size),
        "mean": norm["mean"],
        "std": norm["std"],
        "pipeline_sha256": pipeline_sha256,
        "model_sha256": model["sha256"],
        "execution_provider": provider,
        "registered_providers": providers,
        "runtime": runtime,
        "cpu_fallback_allowed": False,
        "cpu_graph_assignment_allowed": runtime["device"] == "cpu",
        "sdk_affine_metadata": [
            t.get("image_size") for t in transforms if t.get("type") == "TopDownAffine"
        ],
        "geometry_authority": "actual ONNX input and matching SimCC decoder",
    }
    return ColorAlignedPose(backend, transform), evidence
