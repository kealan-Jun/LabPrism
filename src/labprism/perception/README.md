# src/labprism/perception

`baseline.py` 运行按人称接收的检测候选、SAM 2.1 Tiny 框提示逐帧实例分割和 MediaPipe VIDEO 手姿，输出可校验的图像/时间/模型身份与候选结果。检测/SAM 使用 CUDA，手姿使用 CPU。

训练实现与标签在 AnnotationWorkbench。当前无语义分割或 OCR 实现；不存在新训练或已验收准确率。复现见 `docs/INFERENCE-BASELINE.zh-CN.md`。
