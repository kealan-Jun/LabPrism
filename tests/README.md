# tests

运行 `.venv/bin/python -m pytest -q` 检查来源分区/回执、坐标与时间、HTTP 视频范围请求、NAS 挂载/卷身份、发布文件完整性及源码来源。当前 39 项测试通过；这些工程检查不测模型准确率。

`scripts/check_project.py` 检查项目 JSON、依赖和链接。真实浏览器与逐帧视频核验分别使用 `scripts/check_browser.py` 和 `scripts/verify_demo.py`，需要外部运行根中的真实素材；命令见 `docs/DELIVERY.zh-CN.md`。
