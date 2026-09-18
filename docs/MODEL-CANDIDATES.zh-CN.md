# 模型候选比较 · 2026-09-18

当前优先模型能力与真实质量；NPU 转换、量化和实板部署全部后置。以下是研究候选评测，无新训练或正式权重晋级。

## 连续视频结果

在已核验的三个开发片段上复用检测/SAM 基线，新增 RTMPose Hand5 二维手姿、COCO 上下文检测、SegFormer B0 ADE20K 语义预测与因果轨迹关联。每段 80 个分析帧；保留源 PTS、RGB SHA256、生产方回执与父输出。

| 片段 | MediaPipe 有手姿输出帧 | RTMPose 有输出帧 | 新建器材轨迹 / 手轨迹 |
| --- | --- | --- | --- |
| 溶解搅拌第一人称 | 0/80 | 80/80 | 176 / 2 |
| 溶解搅拌第三人称 | 0/80 | 62/80 | 105 / 5 |
| NAS 裸手电脑操作对照 | 80/80 | 80/80 | 19 / 3 |

这些是输出计数，不是关键点 PCK、手检测召回率或身份准确率。抽样原图检查发现关节错位、遮挡错连和缺失；第三人称 18 帧没有通过阈值的手姿输出。NAS 对照不是完整实验。4 个旋转方向的小试仍有明显错位，没有合入。

二维手姿 Z 为 null，左右手未知；显示原始模型分数 ≥0.3 的点，仅在两端达标时画连线。低分手候选和原 MediaPipe 结果留存。轨迹以 IoU/运动预测作同类一对一关联，最长间隔 600ms；丢检不补造框或 mask。大量器材轨迹意味着碎片化风险；HOTA/IDF1 未测。

ADE20K 语义模型已经真实执行，但实验台被大面积错分为墙面/服饰，出现 bus 等错误类别，**不通过实验室语义质量评审**。精确索引 PNG 留存，网页简化轮廓默认关闭并标为失败候选检查。该权重仅准研究/评估，未获得商业部署许可。

## 检测内部回归

生产方冻结导出：AnnotationWorkbench `exports/labprism/model-evaluation-20260918-v1`。97 张完整项目复核图中，仅 18 张 val 用于此次评测，未读取封存测试。16 张第一人称均已有基线接触记录；2 张第三人称为裁剪、接触状态 unknown。相机角色沿用项目复核，原始安装记录未核实。因此只报告内部回归，不能报告独立泛化。

评测使用 FP32（视频检测基线为 FP16），固定 conf=0.25，按同类别、置信度降序、IoU≥0.5 一对一匹配。以下是 micro Precision / Recall，**不是 AP**。

| 视角 | 原配置 960 | 笔记本冲突自动过滤 | 输入分辨率 1280 |
| --- | --- | --- | --- |
| 第一人称，16 图 / 214 标注实例 | 88.07% / 72.43% | 87.93% / 71.50% | 82.78% / 69.63% |
| 第三人称，2 裁剪 / 27 实例 | 100% / 55.56% | 100% / 55.56% | 93.33% / 51.85% |

自动过滤在 NAS 视频压掉了 90 个天平候选，却在固定验证 F073/F074 各删掉一个真实天平：COCO 本身也误把天平识别成笔记本。过滤策略因回归退化被撤回；v2 保留原检测，只记录冲突证据。1280 两个视角均退化，也不替换 960。另一次 augment=True 尝试被上游模型回退为单尺度，记录为无效比较，未作为 TTA 成绩。

## 复现与证据

开发依赖见 `configs/deployment/candidate-requirements.txt`，Python 3.12，检测/语义用 CUDA，RTMPose 实际用 ONNXRuntime CPU。ONNX 只是本次 CPU 推理格式，没有开展 NPU 工作。

```bash
PYTHONPATH=src .venv-inference/bin/python -m labprism.perception.candidate \
  /运行根/runs/baseline-20260917-v2/dissolve-first \
  /运行根/runs/新的候选/dissolve-first \
  --models /运行根/receipts/candidate-models-20260918-v1.json

.venv-inference/bin/python scripts/evaluate_detection.py \
  /生产方/exports/labprism/model-evaluation-20260918-v1 \
  /运行根/evaluations/新的评测 --models /运行根/receipts/candidate-models-20260918-v1.json \
  --candidate higher_resolution
```

不加 `--candidate` 时评测已否决的冲突过滤策略，方便复核失败。评测读取生产方冻结源，不在 LabPrism 另建权威标签或数据集。

运行根 `/home/x1/.local/share/labprism`：

- `runs/candidate-20260918-v2`：240 帧结果、逐帧语义图、父结果/回执；v1 失败策略仍保留。
- `evaluations/detection-regression-20260918-v1/report.json` 与 `detection-resolution-20260918-v1/report.json`：逐图预测、匹配和逐类计数。
- `evaluations/candidate-review-20260918-v2/review.json`：项目代理实际看图范围、错误与决策；非独立人工真值。
- `receipts/candidate-verification-20260918-v2.json`：候选与原基线共 480 帧解码身份检查。
- `evaluations/browser-candidate-20260918-v1/receipt.json`：六个回放入口，真实 Chrome 交互和四种宽度检查。

新增阶段分别为 7.331 / 7.264 / 8.411 分析帧/s；复用了此前检测和 SAM 结果，不能当作完整流水线速度。父阶段时间保存在 `baseline_metrics`，整链路指标保持 null。

## 接下来优先解决

在 AnnotationWorkbench 补齐独立来源的第三人称全图、手套遮挡关键点与实验台语义标注，保留同实验/相邻帧/同步机位分组。当前 all_workbench_training 质量暂停仍有效：需解决或隔离问题批次、补足独立来源验证覆盖并明确父权重。未因运行候选推理而解除。

检测继续聚焦透明/密集器材与背景混淆；手姿以实际可见关节与不可辨状态构建 PCK 评测；追踪需身份真值后评估碎片化与遮挡恢复。长视频、视频 mask 传播、OCR、交互、动作步骤及独立新环境验收仍未完成。
