# 基线依赖与发布边界

2026-09-17 本地诊断。确切安装版本随运行 environment 和运行根 receipts/inference-environment.txt 保存。此清单不是商业许可批准书。

| 组件 | 用途 | 代码许可 / 权重许可 |
| --- | --- | --- |
| PyTorch / TorchVision | CUDA 推理 | BSD 风格代码；CUDA 库独立 NVIDIA 分发条款 |
| Ultralytics 8.4.28 | 历史检测权重及 SAM 包装 | AGPL-3.0；检测权重为项目历史派生候选，源数据与上游权利随生产方记录 |
| SAM 2.1 Tiny | 检测框提示实例轮廓 | 上游 Apache-2.0；转换权重下载自官方 Ultralytics assets；包装许可独立 |
| MediaPipe 0.10.21 | 手部 21 点 VIDEO 模式 | 代码 Apache-2.0；模型来自官方 MediaPipe 分发，公开/商业发布前核对独立模型卡条款 |
| NumPy / SciPy | 数组与依赖运算 | BSD |
| OpenCV 4.x | 图像转换与 mask 轮廓 | Apache-2.0；软件包内第三方组件单独许可 |
| PyAV / FFmpeg | 解码与片段转码 | PyAV BSD；FFmpeg 依编译选项，当前 libx264 转码链有 GPL 组件 |

官方依据：[Ultralytics](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)、[SAM 2](https://github.com/facebookresearch/sam2)、[MediaPipe](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)、[FFmpeg 法律说明](https://ffmpeg.org/legal.html)。

所有片段仅获本地研发使用授权。内部 NAS 保存可复现版本不等于公网发布；当前无商业分发或线上部署验收。源代码不附带用户视频、候选预测、模型或原始训练数据。
