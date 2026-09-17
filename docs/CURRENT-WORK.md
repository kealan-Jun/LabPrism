# 当前工作 · 2026-09-17

最新授权：用户明确网站与算法两部分都做，并要求先命名项目、创建独立文件夹、目录结构和 Agent 规范。项目名采用 **LabPrism / 实验棱镜**。

最新归属纠正：数据集、标注、训练继续由 AnnotationWorkbench 承担；整体项目、官网、算法推理集成、产品验收与部署在 LabPrism。这里不建立重复的训练实现或权威数据集库。按此归属迁出此前临时放在标注项目中的官网和总体计划资料。

## 已完成的初始化

- 建立 `/home/x1/Projects/LabPrism` 独立代码目录、AGENTS.md / Agent.md、README、工作区和 Python 项目定义。
- 官网源代码迁入本项目 `apps/website` 并采用 LabPrism 名称；此前版本及总体计划已从 AnnotationWorkbench 迁出，保存在本项目 `docs/history`、独立运行根和 NAS 历史区。
- 将主排期改为官网线 + 视觉算法线；数据准备为支持工作，飞轮不再是主任务或必做前置。
- 推理、跟踪、理解、几何、产品验收和部署目录建立了职责文档；训练实现继续留在 AnnotationWorkbench。
- 独立 Git 仓库、`.venv` 和 NAS `/mnt/realityloop-nas/LabPrism` 已建立。迁移按 6 组逐文件核对 SHA256，数据集、标注数据库与训练文件未迁出。
- 本地预览已由 LabPrism 的脚本提供；浏览器检查通过首页、技术页、演示页、键盘页签切换和原图弹窗。自动检查覆盖项目入口、JSON、任务依赖、页面链接与脚本语法。
- 后续持续任务已指向 LabPrism 的规范、排期和执行清单；数据/标注/训练任务仍要求在 AnnotationWorkbench 执行。
- 用户已创建 GitHub 仓库 `https://github.com/kealan-Jun/LabPrism.git`，本地 `origin` 已配置。2026-09-17 查询远程尚无 refs；本地尚未创建首次提交或推送。接手提示词位于 `docs/TASK-PROMPT.zh-CN.md`。

## 真实完成边界

网站当前为静态设计预览。使用一张已逐字节校验接收的原始实验图，不含新模型叠加结果；检测/分割/手姿训练和 NPU 部署尚未完成。尚未进行完整手机视口验收。素材交接、迁移和初始化验证记录分别保存在独立运行根 `receipts/website-media-import.json`、`receipts/project-migration-20260917.json` 和 `receipts/bootstrap-verification-20260917.json`。NAS 文档及官网预览包的实际发布内容以 `receipts/bootstrap-publication-20260917.json` 为准。

## 接下来

1. 在 AnnotationWorkbench 选择并交付少量有代表性的实验视频，保留来源、第一/第三人称和质量状态。
2. 在 LabPrism 开始检测、分割与手姿真实推理小试，保存模型、输入和输出身份；需要标注和训练时交由 AnnotationWorkbench 实施。
3. 根据真实输出落实 `packages/contracts`，接入 `apps/viewer` 的连续视频和图层，同时完善官网页面和手机适配。

引用资料和已有实验数据是来源，不代表可修改外部项目。后续执行以本项目 AGENTS.md、ROADMAP 与 backlog 为准；旧工作台的飞轮历史不应覆盖这里的产品方向。
