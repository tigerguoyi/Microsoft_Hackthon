# Phase 0 文件级兼容性审计（本次只实施 Phase 1–3）

审计基准：本地 `codex/unified-decision-analysis`，`27fdfeee5910cc7edcc33b6411b079b4e3a91185`。开始时工作树干净。经用户再次确认，在同一分支验证后 commit，不 push、不部署，不实施 Phase 4–15。

## 当前文件与复用判断

| 文件／模块 | 当前状态 | 本次处理 |
| --- | --- | --- |
| touchline/index.html、app.js | 已恢复 Analysis 双页签，Workspace 是其别名 | 改为独立 view=decisions，旧链接规范化 |
| decision-analysis-view.js、decision-analysis.css | 时间线、筛选、快照、Q2、反事实、AI 完整组件 | 复用；只改路由和页签相关样式 |
| decision-counterfactual.js | 当前受支持 pass/carry/shot 的播放与返回 | 返回独立入口；运动规则不改 |
| decision_analysis/q2.py、comparison.py | 完整 Q2、合法候选、排名与版本绑定 | 原样保留 |
| decision_analysis/tactical_rules.py | 30 个几何特征、战术概率、两步递归、Softmax | 原样保留 |
| decision_analysis/counterfactual.py | 已支持三类动作；直接函数入口校验不完整 | 增加绑定校验，不改运动计算 |
| decision/agents.py | 四角色／Responses；simulate_action 仍只调用 rollout_action | 改为共享完整反事实引擎；只给 Agent 摘要和工具收据 |
| decision_analysis/service.py | 注册状态、API 字段白名单、Key／限额、Agent 投影 | 保持 API 和服务端配置；视频额外字段仍拒绝 |
| server.py、wsgi.py、startup.sh | 本地服务与 Azure WSGI／Gunicorn | server.py 仅增加退休 URL 的 410；wsgi.py、startup.sh 原样保留 |
| public-demo/、build_public_demo.py | 独立旧浏览器评分器、资源与构建脚本 | 删除；保留共享 data/league、decision/value-model.json |
| test_web_port.py | 只检查即将删除的旧浏览器评分器 | 替换为退休 URL 和新主入口测试，不迁移旧评分器 |
| src/demo/pipeline.py、tracking.py、geometry.py、teams.py、possessor.py | 均存在：视觉检测／ByteTrack、RGB、控球人、Homography；pipeline 仍接独立 Softmax | 只审计，不移植、不运行 YOLO、不改变 |
| pyproject.toml | 视频依赖为可选项 | 不改，不新增 CV 依赖 |

## 完整 Q2 的隐含前提

1. 数据 Tracking Schema 要求 14–22 个在场球员，match roster 为 22–28；旧几何 validate 函数虽然接受 2–22，但这不等于完整数据契约接受部分观测。
2. Q2 适配层要求双方各有明确门将和场上非门将；门将会作私有 ID 别名映射，输出映射回真实 ID。
3. 越位线计算读取对方纵向第二名球员；对方数量不足会失败，缺失的防线不能视为没有越位。
4. geometry 对非门将防守者使用 min()、risks[0]：起点压力、最近防守者、接近速度、接收区压力、线路到达时间均依赖已知对方位置。
5. 射门特征读取门将纵深、偏移、封角及线路封堵；不能将未观测门将当成不存在。
6. 失球分支将球权交给预测拦截者／对方控制者；第二步 candidate_actions 遍历状态中的全体在场队友，再求 V1 最大值。只限制第一步不能实现 Partial Q2。
7. Counterfactual 需要 canonical request/public/private/snapshot/metadata，以及球员位置和速度、角色、攻向、期间边界；通过仅保存几名进攻者绕过完整校验是不成立的。

这些前提本次不削弱。视频、部分观测或防守假设标识传入本阶段完整模拟路径时明确拒绝，等待独立 Partial 模式。

## Jolin 参考的实际状态

只读参考 main：`c1f7eddea4843b18e8e50074e7b6a41252503b7d`。
`video-review.html/js/css`、`video-review-model.js`、`video_review/project.py/service.py/geometry.py/storage.py/audit.py` 和 `contracts/video-review.schema.json` 均存在。

指南中的“统一强制 22 人”并非该提交的精确实现：draft roster 接受 **4–22 人**，但双方必须各有确认门将与非门将，并要求所有所选 roster 成员在帧中被观察及人工确认。它仍不能直接表达本计划的“未知门将／未知防守者”的部分观测。

其视频 API 已包含 upload、revision、confirm、analyze、agents、counterfactual、feedback 等；不能在后续 Phase 4 再盲目创建平行接口。本次没有把这些接口或 UI 移入目标仓库。

## 已冻结的回归基准

- 保留上次的 6 个完整 Q2 响应及数值分支基准。
- 新增修改前的 6 个 Counterfactual 完整轨迹 SHA-256：两个比赛状态 × pass/carry/shot。校验增强后必须逐项相同。
- 原始比赛、模型、Q2、参数、Azure 文件不变；Agent 与 Counterfactual 适配器的获准改动单独记版本哈希，不重写数学／数据基准。

后续阶段在统一入口中显示为“未实现”，不能用禁用导航或 mock 工具宣称已经完成视频识别、Partial Q2 或敏感性分析。
