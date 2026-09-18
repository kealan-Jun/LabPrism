# labprism-video-result/1

消费边界：AnnotationWorkbench 导出的 `annotation-workbench-demo-media/1` → LabPrism 推理 → 浏览器。每次接收先验证文件 SHA256、已知人称、train/val 身份；禁止将封存 test/holdout 放入开发演示。标签不随本入口导出，标签 revision 为 null；原始生产方回执和候选身份保留。

- `source`：完整生产方回执，包括原录像 hash、来源组、实验、相机 ID 与独立 role、split、基线接触状态、原尺寸、裁切起点、许可和继承 provenance；另记录本次实际输入 `clip_sha256`。
- `video`：实际 clip width/height、毫秒时长、采样频率、坐标 `clip_pixels_top_left_xy`。不镜像、不旋转；手部 z 是模型相对腕深度，不能当全局度量 3D。
- `models/environment/configuration`：实际权重 hash、生产方回执、执行后端、依赖版本、设备、阈值与推理 batch。GPU 检测/分割与 CPU 手姿分别报告。
- `frames`：严格递增 `frame_index/timestamp_ms`；同时保留解码 PTS/time_base、映射回原录像的 source_timestamp_ms、RGB hash。逐帧检测 `objects`，每个有 frame-local id、原始类别名和显示名、confidence、像素 xyxy box、mask_contours（保留孔洞，SVG evenodd 填充）、nullable mask_score/track_id。当前没有实例跨帧身份承诺。
- `hands`：21 个 `[x_px,y_px,z_relative]`，模型原始左右手输出及其分类分数（不是逐关节置信度），nullable track_id。
- `availability`：任务未执行和执行但空检分开。SAM 轮廓是检测框提示的逐帧实例分割，不冒充语义或视频传播分割。
- `events`：当前为空，定位点不是动作事件。不存在识别结果时禁止前端合成字幕或图层。
- `metrics`：效果、泛化、时序质量、NPU 均为 null；壁钟吞吐包含离线采样解码及推理，不是摄像头全帧实时 FPS。首帧包含初始化，warm p50 单独列出。

浏览器在视频呈现时间查找最近的**不晚于当前时刻**预测；超过 150 ms 不显示过期框。逐分析帧跳转仅定位已推理帧。不同机位暂不同步、不关联身份。

执行 `labprism.contracts.validate_result` 检查时序、源片段映射、边界、有限值与实例 ID。每次运行保留结果/媒体/模型回执 SHA256、实现文件 hash 和源码 commit。源码归档没有 Git 时 commit/dirty 为 null，使用 `source_release` 保留包内源码提交及归档/版本清单 SHA256，不借用启动命令所在目录的 Git。目录拒绝覆盖，历史运行保留。
