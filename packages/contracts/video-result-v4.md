# Video result / 4

`labprism-video-result/4` 在 v3 的实际帧、实例、手姿、文字、时序 mask 和二维接近证据上增加用途、时钟、坐标链及独立输出状态。`validate_result` 继续读取 v1/v2/v3；历史文件不被自动改写为 v4。

## 用途与来源

`data_use.purpose` 为 `development`、`evaluation` 或 `production_observation`。

| 用途 | source.split |
| --- | --- |
| development | train 或 val |
| evaluation | 原始 train / val / test / holdout；调用方仍须遵守封存授权 |
| production_observation | 必须为 null；生产观察不自动成为训练数据 |

`camera_id` 与 `camera_role` 分开，后者允许 unknown。未知机位不提供独立视角支持。同来源裁剪不是新相机，轨迹 ID 不等于登记仪器 ID。模型、输入 SHA256、运行回执和父结果继续保留。

## 时钟与坐标

`time_mapping` 明确包含 `clip_origin_ms`、`capture_origin_ms`、`global_origin_ms`。缺失的采集/全局时钟为 null。每帧 `clip_pts` 与有理数 `time_base` 必须满足 `timestamp_ms = clip_pts × time_base × 1000 - clip_origin_ms`，不能以名义 FPS 重建变帧率时间。原片时间另按原片截取起点校验。

`coordinates.clip_to_source` 是有限、可逆 3×3 变换；`operations` 记录裁剪、缩放、填充、镜像、旋转等实际操作。手姿旋转候选使用同一 ROI，在旋转后的实际像素上推理，再以逆矩阵还原。二维手姿深度保持 null；局部相对深度不代表标定全局 3D。

## 词典与输出状态

`semantic_taxonomy` 有 `id`、`version`、`classes`、`unknown_id` 和 `ignore_id`。类别 ID 不限定为 ADE20K 范围；ignore 不得混入评价类别。每帧像素图的 taxonomy、文件与 SHA256 及区域类别必须与该词典一致。

`output_statuses` 分别记录 boxes、instance_masks、semantic_map、keypoints、tracks、relations、events、readouts 的 `state` 和非空 `reason`。状态为 predicted / no_detection / not_run / not_connected / failed / not_applicable。有实际输出的模块不能同时声明 unavailable/failed。predicted 只表示模型输出，不表示质量通过。上游 completed、PARTIAL_EVIDENCE 和登记绑定均保留原有语义。

## 浏览器投影

原始运行文件和回执不变；本地预览另生成 `labprism-result-index/1` 和 `labprism-frame-chunk/1`。默认每块最多 5 秒、50 个分析帧，可配置上限为 30 秒、100 帧。索引包含每块时间、字节数、SHA256；客户端校验文件名、大小、hash 及帧时间，一次最多两个在途块，缓存最多三个块。切换素材取消旧请求，失败块不连续重试，用户可明确重试，原视频仍可播放。

初始索引不带逐帧几何。文字导航最多 2000 条、事件导航最多 2000 条，超出时记录截断状态；事件只带证据帧数，不重复加载全部逐帧关系。完整下载仍保留全量事件与实际证据。公开元数据投影去除本地模型/素材路径和命令；该机制不构成私有视频的公开发布授权。
