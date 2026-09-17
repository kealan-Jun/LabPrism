# LabPrism · 实验棱镜

**看清器材，追踪动作，理解实验。**

LabPrism 是独立的实验视觉项目，包含两条同时推进的主线：

1. **完整官网与演示体验**：首页、技术能力页、演示空间及后续可交互的视频查看界面。
2. **真实视觉算法系统**：检测、实例/语义/视频分割、手部姿态与追踪、器材交互、动作/步骤理解、OCR、空间几何与 GPU/NPU 部署。

以 Transfyr 公共演示的能力和体验作为参考，使用自己的实现与实验素材，以可复现测试改进效果。NAS 数据和标注工具为算法研发提供支持，旧数据飞轮不作为本项目主交付或前置条件。

## 当前状态

2026-09-17：独立仓库、目录、规范、双线排期与本地运行入口已建立。官网首页、技术页、演示页有静态预览，使用自有实验原始图片；新模型输出、连续视频和动作时间线尚未接入。暂无本项目新训练模型、已验收算法精度或 NPU 部署。

项目名 LabPrism 为本项目采用的名称，不包含域名可用性或商标检索结论。

## 入口

- [接手任务提示词](docs/TASK-PROMPT.zh-CN.md)
- [GitHub 仓库](https://github.com/kealan-Jun/LabPrism)
- [代理规范](AGENTS.md) / [Agent.md 入口](Agent.md)
- [架构与目录约定](docs/ARCHITECTURE.zh-CN.md)
- [8 周双线排期](docs/ROADMAP.zh-CN.md)
- [当前工作与下一步](docs/CURRENT-WORK.md)
- [执行清单](docs/backlog.json)
- [NAS 与数据交接规则](docs/STORAGE.zh-CN.md)
- [算法能力矩阵](docs/CAPABILITIES.zh-CN.md)

## 本地预览

无需安装前端依赖。Python 3.11+：

```bash
cd /home/x1/Projects/LabPrism
python3 scripts/check_project.py
python3 scripts/preview_website.py --port 8031
```

访问 `http://127.0.0.1:8031/`。脚本只发布独立静态目录到本机回环地址，不暴露数据库、NAS 根或整个工作数据目录。图片由已接收的预览素材包提供；全新机器需要先取得相应素材回执。

本项目推理环境使用 `.venv`；基础仓库当前没有强制安装 Torch、CUDA 或教师模型，后续按实测兼容性建立推理环境。数据集、标注工具、训练器、训练环境与原始训练记录继续由 AnnotationWorkbench 负责，不在这里重复建设。

## 存储位置

| 内容 | 位置 |
| --- | --- |
| 代码、网页、规范与配置 | `/home/x1/Projects/LabPrism` |
| 推理缓存、接收的推理模型、预览素材与产品证据 | `/home/x1/.local/share/labprism` |
| 总体文档、官网/部署包、推理权重副本与产品验收 | `/mnt/realityloop-nas/LabPrism` |
| 数据集、标注、训练与原始训练记录 | AnnotationWorkbench 及其已有本地/NAS 数据根 |

数据、标签、预测和权重不放进 Git。LabPrism 经版本化交付接收推理权重、素材和训练回执引用，权威数据集与训练记录仍在标注项目。NAS 目录存在不代表模型已交付，实际内容以回执为准。
