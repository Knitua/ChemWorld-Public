# 因果世界

> **ChemWorld 的独特之处并不是任务多，而是能在不同、可审计的隐藏规律下运行同一公开任务。**

在固定模拟器中获得高分，无法区分 Agent 学会了实验，还是只学会了那个模拟器。ChemWorld 可以改变已注册的速率、构成关系或装置边界，同时保持公开任务、动作语言与仪器语义不变。

## World、Task、Scenario 与 Seed

| 概念 | 含义 |
| --- | --- |
| World | 隐藏因果规律：动力学、相态、设备与观测生成 |
| Task | 公开实验问题、权限、预算与成功标准 |
| Scenario | 含初始状态和声明干预条件的 Task–World 组合 |
| Seed | 用于重建实例的确定性索引 |

改变 seed 通常改变实例随机性，而不是因果结构。因此，多 seed 稳健性并不等价于对变化世界的适应。

## 稳定公开合同

在受控 fork 两侧，Agent 看到相同的任务目标、有类型操作和仪器含义。它不会获得 world 标签或私有机理参数。如果发生适应，应当通过选择的测量、修正后的决策和下游结果体现。

## 一个最小例子

在同一个反应任务中，升温可能主要加快目标路径、放大竞争路径，或暴露设备限制。固定配方无法区分这些解释；实验 Agent 必须选择能够区分它们的证据。

## Public v0.4 验证了什么

冻结版本包含 6 对匹配 parent/child world 和 24 条轨迹。每对只改变一个已注册私有组件，执行声明的固定公开策略，并通过精确回放审计。这建立了声明模型域内的受控软件世界干预；它不证明候选 Agent 能识别所有变化，也不证明能够迁移到物理系统。

实现细节见[世界组合合同](world-composition-contract.md)、[组合覆盖](world-composition-coverage.md)和[受控世界 Protocol](https://github.com/Knitua/ChemWorld-Public/blob/main/protocols/controlled-world-forks.md)。

下一步：[系统模型](architecture.md) · [展示世界](worlds.md) · [真实世界桥接](real-world-bridge.md)
