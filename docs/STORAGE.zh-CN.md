# 数据与 NAS 目录约定

代码根为 `/home/x1/Projects/LabPrism`；本地运行根为 `/home/x1/.local/share/labprism`；NAS 自有根为 `/mnt/realityloop-nas/LabPrism`。禁止将原相机目录、AnnotationWorkbench 数据库或其他项目目录当作可随意修改的本项目空间。

```text
~/.local/share/labprism/
  media/website/          已接收的官网预览图片字节
  website-preview/        本机静态发布目录
  cache/                 有容量上限的可重建缓存
  runs/                  正在执行的推理与产品验收
  logs/                  本地进程日志
  receipts/              交接、校验和执行证据

NAS / LabPrism/
  .labprism-volume.json   项目与卷身份
  README.zh-CN.md         当前实际内容和目录入口
  documents/             排期、规范和版本化说明
  sources/               只读原视频的来源清单；不移动相机原件
  media/                 本项目明确接收的素材副本
  models/                已接收的推理权重副本 / <task>/<view>/<version>/<backend>/
  evaluations/           <benchmark>/<model-release>/
  releases/              <version>/ 官网与运行包
  receipts/              交接清单与 SHA256 校验
```

LabPrism 不建立权威 datasets 或训练目录。数据集、标注、训练检查点和原始训练记录均留在 AnnotationWorkbench。LabPrism 的 `models`、`evaluations` 可以暂时只有说明文件；只有完成真实推理权重交付或产品验收后才增加版本。不可伪造 READY 或训练结果。

## 交接流程

外部生产方保留原数据。LabPrism 接收明确文件清单、许可/用途、源项目/任务、原始 SHA256、分区和标注身份，复制到自有目录后逐字节核验并保存 receipt。首次预览图片只用于本地设计展示，原图没有接受或更改标注，不等同于接收训练数据集，也不授权公开发布实验素材。

数据集交付引用携带生产方 release、类别/schema、分区和复核状态；权威数据仍在生产方。推理模型副本携带父权重/数据版本引用、运行配置、环境、生产方训练指标和适用视角。LabPrism 产品评测与部署结果独立留证，不改写生产方训练日志。

NAS 写入前必须确认 `/mnt/realityloop-nas` 确实为挂载点、目标在挂载内、卷身份匹配且不是重定向到其他项目的符号链接。发布先复制并核验，再更新回执，保留历史版本。
