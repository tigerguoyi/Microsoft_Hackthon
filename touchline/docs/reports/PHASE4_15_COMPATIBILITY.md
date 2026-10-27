# Phase 4–15 开工审计

基准 `389fb1f3736febaaa53d77477a098d3177aa57bf`，当前分支 `codex/unified-decision-analysis`，工作树干净。仅修改用户本地 Microsoft_Hackthon，不推送或部署。

- 完整 Q2 的 q2.py、tactical_rules.py、comparison.py、xT及训练模型、原比赛保持原件。
- 原四角色 Team / Responses / 配额 / Reviewer 复用；增加独立 evidence_adapter，不将视频伪装为合成 contract-1。
- 原反事实动作循环提取成 motion.py，完整比赛仍通过原校验入口；部分模式独立校验并显式标注假设。原6条完整轨迹基准必须相同。
- Jolin 视频设计参考 c1f7eddea4843b18e8e50074e7b6a41252503b7d，复用 geometry 的校准函数和不可变revision设计；不迁移原 reconstruct 的完整22人评分门槛。
- src/demo 现有 pipeline 同时加载分类器，不能直接把其输出当 Q2；新增 observations 专门复用 ByteTrack、TeamBook、PossessorTracker 和 Homography，完全不导入分类器。
- 普通服务不导入 cv2/Torch/YOLO。媒体校验和视觉计算只在限时子进程运行。Azure公开入口默认关闭，后续 worker与多用户鉴权需单独部署。
- 原环境无CV依赖及权重；将其安装/下载至临时验证环境，不写入普通依赖和Git。真实模型验证与mock单元测试分开记录，不预先声称识别成功。
