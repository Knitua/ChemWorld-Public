# 确认性任务

确认性任务是本版本中为最严格受控评估设计保留的两个公开任务合同：

| 任务 | 公开实验问题 | 交互层级 |
| --- | --- | --- |
| `reaction-to-crystallization` | 利用反应终检调整带晶种冷却轨迹，再分离产物并权衡收率、纯度和粒径分布 | Campaign |
| `electrochemical-conversion` | 选择有边界的介质和电解质条件，在电荷、能耗与风险记账下优化选择性转化 | Campaign |

## 这里的“确认性”意味着什么

它标识一种**任务角色**，不是已经发布的赢家。任务合同、合法操作、公开仪器、预算、终止规则、软件资格测试与回放边界足以支持预注册比较；方法选择、训练数据、资源公平性、seed 与统计声明仍属于具体评估协议。

## 公开证据

Public v0.4 发布：

- 任务卡与有类型动作/观测合同；
- 确定性运行时与回放测试；
- 参考及生成世界组合资格结果；
- 净化后的有限证据及构建 Protocol；
- 明确的局限性与证据分母。

它不发布 Participant 排名、仅开发环境可见的 gate、私有确认材料或 v0.5 candidate 结果。在 Lab 中由单个 seed 得到的分数只是交互演示，不是确认性 Benchmark 结果。

## 最小比较合同

正式研究应预先声明冻结版本、任务合同哈希、world/scenario split、seed、Agent 身份、允许反馈、实验与方法资源、失败处理、主要任务特定结果以及回放验证。风险、成本、适应和自主性应分开报告，不能把不同量纲压缩为一个普适分数。

继续阅读 [Benchmark 设计](benchmark-design.md)、[证据与当前状态](evidence.md)和公开 [Protocol](https://github.com/Knitua/ChemWorld-Public/tree/main/protocols)。
