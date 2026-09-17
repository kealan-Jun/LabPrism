#!/usr/bin/env python3
"""Validate project entry points, task dependencies and website links without training."""

from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlsplit, unquote


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids = []
        self.references = []
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for name in ("src", "href"):
            if attrs.get(name):
                self.references.append(attrs[name])
        if tag == "img" and not attrs.get("alt"):
            raise ValueError("图片缺少 alt")


def main():
    root = Path(__file__).resolve().parents[1]
    for name in ("AGENTS.md", "Agent.md", "README.md", "docs/ROADMAP.zh-CN.md", "docs/CURRENT-WORK.md"):
        assert (root / name).is_file(), name
    for path in root.rglob("*.json"):
        if not any(p.startswith(".") for p in path.relative_to(root).parts):
            json.loads(path.read_text())
    tasks = json.loads((root / "docs/backlog.json").read_text())["tasks"]
    ids = {task["id"] for task in tasks}
    assert len(ids) == len(tasks)
    done = set()
    while done != ids:
        ready = {task["id"] for task in tasks if set(task["depends_on"]) <= done}
        assert ready - done, "任务依赖有缺失或循环"
        done |= ready
    site = root / "apps/website"
    pages = {path.name: Page(path) for path in site.glob("*.html")}
    for name, page in pages.items():
        assert len(page.ids) == len(set(page.ids)), name
        for ref in page.references:
            parsed = urlsplit(ref)
            if parsed.scheme or parsed.netloc:
                continue
            path = unquote(parsed.path) or name
            if path == "assets/lab-scene.png":
                continue  # Runtime asset verified by preview_website.py against its receipt.
            target = (site / path).resolve()
            assert target.is_relative_to(site.resolve()) and target.is_file(), (name, ref)
            if parsed.fragment:
                assert parsed.fragment in pages[target.name].ids, (name, ref)
    for path in [*root.glob("scripts/*.py"), *root.glob("src/**/*.py")]:
        compile(path.read_text(), str(path), "exec")
    print(json.dumps({"project": "LabPrism", "pages": len(pages), "tasks": len(tasks), "checks": "passed", "algorithm_validation": "not_run"}))


if __name__ == "__main__":
    main()
