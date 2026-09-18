# 本地验证与内部交付

本机预览 `http://127.0.0.1:8031/demo.html`。私有实验素材只用于本地研发与内部 NAS 留档，没有公网发布。

## 预览服务

本机已安装 `configs/deployment/labprism-preview.service` 到用户级 systemd，固定使用项目 `.venv`，要求 Python 3.11+。网页源码修改后准备静态目录；服务端代码修改后重启单一服务：

```bash
python3 scripts/preview_website.py --prepare-only
systemctl --user restart labprism-preview
systemctl --user status labprism-preview
```

新机器需先建立环境、接收素材及推理回执，再按实际工作目录安装该 unit。用户登录会话的服务管理不等于生产部署或已完成整机重启验收。

## 真实检查

```bash
python3 scripts/check_project.py
.venv/bin/python -m pytest -q
# pip install -e '.[browser]'；使用本机 Chrome，无需另下载浏览器
.venv/bin/python scripts/check_browser.py --output /外部运行根/evaluations/新的浏览器版本
.venv-inference/bin/python scripts/verify_demo.py /home/x1/.local/share/labprism/receipts/demo-catalog-baseline-20260918-v2.json --compare-root /home/x1/.local/share/labprism/runs/reproduction-20260918-v2 --output /外部运行根/receipts/新的核验回执.json
```

浏览器脚本使用真实输入核对叠加坐标、骨架点数、逐帧定位、播放/暂停、倍速、图层/原画、实例详情、下载、失败恢复和四种宽度。所有截图与运行回执写到代码库外。图像/时间一致及重复运行一致不等于模型准确。

## NAS 版本包

先提交审查后的源码，再执行内部发布；脚本拒绝脏工作区、未挂载/错误卷、覆盖已有版本、损坏模型或不一致的源记录：

```bash
python3 scripts/publish_local_release.py 一个新版本 --evidence /home/x1/.local/share/labprism/evaluations/browser-20260918-v2 --evidence /home/x1/.local/share/labprism/evaluations/review-20260918-v1
```

包内包含 `website/`、`runs/`、`media/`（已接收的推理输入副本）、`models/`（推理权重副本）、`documents/`、`evaluations/`、`receipts/`、`code/source.tar.gz` 和路径可迁移的 `replay.json`。权威数据集与原始训练记录不迁移。`release.json` 列逐文件 hash，全部回读一致后才写 `READY.json`；中断留下的无 READY 目录不是已交付版本，不自动清除。

将源码归档解到新代码目录，按依赖文件建立 `.venv-inference`，即可在另一受授权机器验证或复跑：

```bash
python3 scripts/replay_release.py /内部版本包 --verify-only
PYTHONPATH=src .venv-inference/bin/python scripts/replay_release.py /内部版本包 /外部运行根/runs/新的复跑版本 --clip dissolve-first
```

复跑读取包内素材/权重，写新的运行目录与重定位回执，原始生产方记录保留。要求真实 CUDA；手姿实际运行于 CPU。该包是离线诊断演示交付，没有模型晋级、商业发布、量化或 NPU 实板完成含义。

## 研究候选包

候选包保留原基线，按每个 run 的真实模型清单打包权重及辅助配置/许可。`parents/` 保存可核验的完整父运行，`replay.json` 标记 `mode=candidate`。重放候选使用包内父预测和新阶段权重，不把复用父阶段当作整链路重跑速度。安装 `candidate-requirements.txt`，使用 `--clip dissolve-first-candidate`；旧基线入口仍可完整重跑。

研究候选含不合格语义与未验收手姿/轨迹，READY 仍只表示文件完整。SegFormer 为研究/评估限定许可，不得据此认为模型已可商用。NPU 全部后置。
