# configs/deployment

`inference-requirements.txt` 固定真实 GPU/CPU 基线依赖；`labprism-preview.service` 使用项目 `.venv` 启动本地 8031 预览，运行方法见 `docs/DELIVERY.zh-CN.md`。

NPU 型号、SDK、量化和实际执行提供器尚未验收；当前配置不代表实板部署完成。

## CUDA 手姿重算

`scripts/setup_pose_cuda_runtime.py --base-python .venv-inference/bin/python --output LOCAL_RUNTIME --receipt NAS_RECEIPT.json` 创建独立 ONNX Runtime GPU 1.26.0 环境，通过显式 `.pth` 复用原推理环境中的 PyTorch CUDA 12、rtmlib、PyAV 等依赖，不修改原环境或生产服务。使用新环境的 `bin/python` 运行重算脚本。基础环境应保持版本固定；更改后需重新资格验证。包的 provider 列表本身不代表实际 GPU 推理成功。

`run_trained_hand.py` 的请求可加入 `"runtime":{"device":"cuda","device_id":0,"gpu_memory_limit_mb":1024}`。创建会话和实际执行均禁止静默 CPU 回退；缺少兼容库时直接失败。1024 MiB 是 ORT arena 上限，不包括 CUDA context 和库的全部显存。旧请求默认 CPU，便于复现历史结果。比较入口 `compare_pose_runtime.py` 检查同权重、同 ROI、同颜色/方向变换下的输出与已知关节，不以更换后端代替模型精度验收。
