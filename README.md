# LabPrism · 实验棱镜

**看清器材，追踪动作，理解实验。**

LabPrism 是独立的实验视觉项目，包含两条同时推进的主线：

1. **完整官网与演示体验**：首页、技术能力页、演示空间及后续可交互的视频查看界面。
2. **真实视觉算法系统**：检测、实例/语义/视频分割、手部姿态与追踪、器材交互、动作/步骤理解、OCR、空间几何与 GPU/NPU 部署。

以 Transfyr 公共演示的能力和体验作为参考，使用自己的实现与实验素材，以可复现测试改进效果。NAS 数据和标注工具为算法研发提供支持，旧数据飞轮不作为本项目主交付或前置条件。

## 当前状态

2026-09-18：三页官网已接真实视频查看器；三段开发素材各有原基线/候选两组回放，可逐帧查看检测、SAM 轮廓、手姿、轨迹、语义失败样例和类别冲突。Chrome 六组回放及 320/390/768/1440 宽度检查通过。

RTMPose 候选使两段戴手套片段的有手姿输出帧从 0/80 分别增至 80/80、62/80，但关节错位与缺失仍在；语义候选域内表现不合格。固定 18 图内部检测回归否决了误伤真实天平的冲突过滤和退化的 1280 分辨率配置。详见 [模型比较与复现](docs/MODEL-CANDIDATES.zh-CN.md)。

当前专注模型能力，NPU 全部后置。没有新训练、独立泛化成绩或正式模型晋级；完整长视频、视频传播分割、动作/OCR 和 v0.1/v1.0 尚未验收。

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
.venv/bin/python scripts/preview_website.py --port 8031
```

访问 `http://127.0.0.1:8031/`。脚本只发布独立静态目录到本机回环地址，不暴露数据库、NAS 根或整个工作数据目录。图片由已接收的预览素材包提供；全新机器需要先取得相应素材回执。

本机已有用户级 `labprism-preview.service` 管理 8031 预览；先用 `systemctl --user status labprism-preview` 检查，避免重复启动。服务配置与验证/内部发布说明见 [交付与复现](docs/DELIVERY.zh-CN.md)。

`.venv` 用于开发/浏览器检查；独立 `.venv-inference` 使用 Python 3.12、PyTorch CUDA、SAM 2.1 Tiny 和 MediaPipe。安装与基线复现见 [真实视频基线](docs/INFERENCE-BASELINE.zh-CN.md)。数据集、标注工具、训练器、训练环境与原始训练记录继续由 AnnotationWorkbench 负责。

## 存储位置

| 内容 | 位置 |
| --- | --- |
| 代码、网页、规范与配置 | `/home/x1/Projects/LabPrism` |
| 推理缓存、接收的推理模型、预览素材与产品证据 | `/home/x1/.local/share/labprism` |
| 总体文档、官网/部署包、推理权重副本与产品验收 | `/mnt/realityloop-nas/LabPrism` |
| 数据集、标注、训练与原始训练记录 | AnnotationWorkbench 及其已有本地/NAS 数据根 |

数据、标签、预测和权重不放进 Git。LabPrism 经版本化交付接收推理权重、素材和训练回执引用，权威数据集与训练记录仍在标注项目。NAS 目录存在不代表模型已交付，实际内容以回执为准。
