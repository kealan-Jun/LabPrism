#!/usr/bin/env python3
"""Prepare and serve only LabPrism's local website bundle, never the data root."""

import argparse
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil


def prepare(project, data_root):
    source = project / "apps/website"
    destination = data_root / "website-preview"
    receipt = json.loads((data_root / "receipts/website-media-import.json").read_text())
    asset = data_root / "media/website/lab-scene.png"
    if asset.is_symlink() or hashlib.sha256(asset.read_bytes()).hexdigest() != receipt["sha256"]:
        raise ValueError("预览素材身份校验失败")
    if destination.is_symlink():
        raise ValueError("预览目录不能是符号链接")
    destination.mkdir(parents=True, exist_ok=True)
    assets = destination / "assets"
    if assets.is_symlink():
        raise ValueError("预览 assets 目录不能是符号链接")
    assets.mkdir(exist_ok=True)
    for path in source.iterdir():
        if path.is_file() and path.suffix in {".html", ".css", ".js"}:
            target = destination / path.name
            if path.is_symlink() or target.is_symlink():
                raise ValueError("预览文件不能是符号链接")
            shutil.copyfile(path, target)
    target_asset = assets / "lab-scene.png"
    if target_asset.is_symlink():
        raise ValueError("预览图片不能是符号链接")
    shutil.copyfile(asset, target_asset)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8031)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    data_root = Path(os.environ.get("LABPRISM_DATA_ROOT", str(Path.home() / ".local/share/labprism"))).resolve()
    directory = prepare(project, data_root)
    if args.prepare_only:
        print(directory)
        return
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"LabPrism local preview: http://127.0.0.1:{args.port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
