#!/usr/bin/env python3
"""Install an isolated CUDA ORT overlay, reusing the existing inference packages.

The base environment is read-only. The overlay's own site-packages take priority
over its explicit base-runtime .pth. Do not install both ORT distributions into
the same directory: they share the onnxruntime import package.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is required")
    if args.output.exists() or args.receipt.exists():
        raise SystemExit("Choose a new runtime and receipt path")
    base = args.base_python.absolute()
    query = """import json,site,sys,torch,rtmlib,onnxruntime,numpy,av,importlib.metadata as m
print(json.dumps({'python':sys.version,'site':site.getsitepackages()[0],
'torch':torch.__version__,'cuda':torch.version.cuda,'numpy':numpy.__version__,
'rtmlib':m.version('rtmlib'),'av':av.__version__,'base_ort':onnxruntime.__version__}))
"""
    before = json.loads(subprocess.check_output([str(base), "-c", query], text=True))
    if not (before["cuda"] or "").startswith("12.") or before["rtmlib"] != "0.0.16":
        raise SystemExit("This overlay requires the pinned CUDA 12 / rtmlib 0.0.16 base")
    subprocess.run([uv, "venv", "--python", str(base), str(args.output)], check=True)
    python = args.output.absolute() / "bin/python"
    subprocess.run([uv, "pip", "install", "--python", str(python), "--no-deps",
                    "onnxruntime-gpu==1.26.0"], check=True)
    site = Path(subprocess.check_output(
        [str(python), "-c", "import site;print(site.getsitepackages()[0])"], text=True
    ).strip())
    (site / "labprism-base-runtime.pth").write_text(before["site"] + "\n")
    after = json.loads(subprocess.check_output([str(python), "-c",
        "import json,onnxruntime as o,torch;print(json.dumps({'ort':o.__version__,"
        "'ort_module':o.__file__,'torch':torch.__version__,'torch_module':torch.__file__,"
        "'available_providers':o.get_available_providers()}))"], text=True))
    if not Path(after["ort_module"]).is_relative_to(args.output.absolute()):
        raise SystemExit("Overlay ORT did not win import resolution")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps({
        "schema_version": "labprism-cuda-runtime/1", "base_python": str(base),
        "python": str(python), "base": before, "overlay": after,
        "base_modified": False, "actual_cuda_inference_verified": False,
        "note": "Provider listing is not successful GPU inference; replay must fail closed.",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
