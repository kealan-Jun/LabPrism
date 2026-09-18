# apps/viewer

真实离线视频查看器由官网 `demo.html` 加载：播放/暂停/倍速、逐分析帧、原画对照、检测/实例轮廓/手姿图层、实例详情与结果下载。读取 `labprism-video-result/1`，不生成或补画缺失预测。

当前使用三段约 8 秒的开发诊断输入，已通过真实 Chrome 检查。持续轨迹、OCR、动作证据时间线与完整长视频仍待实现，详见 `docs/CURRENT-WORK.md`。
