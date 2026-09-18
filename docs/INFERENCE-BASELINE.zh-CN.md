# 首个真实视频基线

本地诊断路径使用已有第一/第三人称检测候选 + SAM 2.1 Tiny 框提示分割 + MediaPipe Hand Landmarker。没有训练器或新数据集迁入 LabPrism。检测候选来自 AnnotationWorkbench 2026-09-16 的模型交接；它们不是已验收部署权重，不采用问题伪标签批次训练后的“current”作为产品晋级。

## 环境与复现

```bash
cd /home/x1/Projects/LabPrism
uv venv --python 3.12 .venv-inference
uv pip install --python .venv-inference/bin/python -r configs/deployment/inference-requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124
PYTHONPATH=src .venv-inference/bin/python -m labprism.perception.baseline \
  /home/x1/.local/share/labprism/media/demo-v1/dissolve-first \
  /home/x1/.local/share/labprism/runs/自选新版本/dissolve-first \
  --models /home/x1/.local/share/labprism/receipts/baseline-models-20260917.json
python3 scripts/preview_website.py --prepare-only
```

新机器先取得 producer 素材和模型回执，不能仅凭代码构造输入。运行输出不可覆盖。演示清单位于运行根 `receipts/demo-catalog.json`，只包含已验证的 run 引用；预览服务器复制所选 result.json/clip.mp4，不暴露整个运行根。

现阶段素材为两个同实验 train 组的 8 秒裁切片段，以及一个 NAS 裸手操作电脑的 8 秒诊断对照；都不是三段完整实验，也不构成跨环境泛化验收。采样频率 10 Hz。所有预测均为候选，缺失关键点原样保留。

## 模型与许可来源

- [SAM 2 上游](https://github.com/facebookresearch/sam2)：上游代码/权重说明为 Apache-2.0；本轮使用 [Ultralytics SAM 2.1 接口](https://docs.ultralytics.com/models/sam-2/)，其包装代码适用 AGPL-3.0，许可分别记录。
- [MediaPipe 手姿 Python 接口](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)与[模型说明](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)：VIDEO 模式、CPU/XNNPACK、最多双手，21 个点。代码 Apache-2.0；独立模型卡和分发条件随模型来源留存，尚未作商业发布审核。
- 项目检测权重保留来源 SHA256 和原交接回执，历史训练细节仍归生产方；不在这里编造完整训练恢复记录。

后续应按错误样例在 AnnotationWorkbench 补足验证与标签，再比较改进候选；当前不解除生产方训练暂停。下一项优先是跟踪与视频分割对照、独立语义模型小试及稳定的全片视频，再接 OCR/事件。NPU 板卡、量化与实板都未完成。

## 2026-09-18 接手验收

修复 PyAV 关闭容器后读取时长的问题，重新执行三段（240 分析帧）。所有源帧 PTS/RGB hash 一致，所有预测载荷与原基线逐帧一致；复跑回执在运行根 `receipts/reproduction-verification-20260918-v2.json`。两人称戴手套片段均未检出手姿；裸手对照有输出，同时保留屏幕误检。

初始 `reproduction-20260918-v1` 第三段未完成；失败目录和日志保留。最终 `reproduction-20260918-v2` 三段均成功。浏览器和完整包复跑命令见 [交付说明](DELIVERY.zh-CN.md)。
