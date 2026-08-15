# 系统模型

ChemWorld 分离物理真值、实验交互和研究目标，从而避免把评测者持有的隐藏状态泄露给 Agent，也避免把任务得分误当作物理量。

## 三层系统

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| 物理因果世界 | 有类型状态、隐藏转移、构成规律、设备、观测生成与受控干预 | 任务目标、Agent 信念或排名 |
| 实验交互运行时 | 动作合法性、原子事务、生命周期、测量、失败、资源与可回放轨迹 | 为 Agent 选择动作或静默修复 |
| 任务与评估合同 | 公开目标、权限、预算、终止与任务特定评估 | 运行时物理或泄露隐藏真值 |

## 规范层级

```text
Campaign
└── Experiment
    └── Operation / Measurement
```

一个 campaign 是一个 **Task × Scenario × Agent × Seed** 单元。Experiment 从显式初始化状态开始，在 final assay、显式终止、失败或预算截断时结束。只有合同有效的 final assay 才是可比较的正式终点；失败和未完成尝试仍保留在轨迹中。

## 三种动作抽象

- **Campaign Design：** 选择完整配方或实验。
- **Procedure Execution：** 每次选择一个合法操作。
- **Process Control：** 选择有边界的设备设定点或过程动作。

Public v0.4 通过同一套任务与运行时合同支持这些抽象。Process Control 是有边界的设定点抽象，并非普适高频连续控制声明。

## 原子校验

操作提交前，运行时检查 Schema、任务权限、参数边界、装置状态、物料前置条件与剩余资源。被拒绝的操作会返回公开原因，不改变状态或预算；已提交操作则同时更新物料、装置、资源和事件账本。

## 结果分层

轨迹区分：

- `environment_outcome`：世界与运行时实际产生的结果；
- `agent_visible_observation`：当前信息条件实际释放的观测；
- `evaluation_outcome`：绑定后的终点与评估字段。

改变反馈可以改变可见层，但不能重写底层环境或评估结果。

## 有边界的完整性

ChemWorld 追求在选定物理化学原型上实现实验交互链的结构完整性。化学覆盖与数值保真度有明确边界，而非穷尽。

下一步：[API 参考](reference.md) · [Benchmark 设计](benchmark-design.md) · [适用边界](limitations.md)
