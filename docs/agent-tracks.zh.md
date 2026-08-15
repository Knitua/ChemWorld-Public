# Agent 交互层级

ChemWorld 在同一套世界与任务合同上支持三个交互层级。它们回答不同问题；除非有明确换算协议，否则不应共用一个排行榜。

## Track A — Campaign Design

Agent 提交完整实验或配方。这是黑箱优化、实验设计与跨实验适应的最短路径。

**Agent 负责：** 配方选择、测量计划和实验间预算分配。  
**运行时负责：** 合法执行、状态转移、资源记账与最终评估。

## Track B — Procedure Execution

Agent 每次选择一个操作：投料、设定条件、测量、后处理、恢复、终止和请求 final assay。

这一层级显式考察流程自主性。即使配方很好，无法满足前置条件或闭合生命周期的 Agent 也不会被系统静默补救。

## Track C — Process Control

Agent 在世界演化时选择有边界的设备设定点或过程动作，适用于流动、电化学及其他控制轨迹重要的任务。

Public v0.4 实现的是有边界设定点/过程抽象，并非普适高频控制器，也不模拟所有真实执行器。

## 共享合同

三个 Track 都绑定相同的公开任务标识、world/scenario split、资源账本、事务语义、回放规则与证据边界。隐藏真值始终由评测者持有。

## 浏览器与 Python 入口

[Student Lab](student-lab.md) 开放合法操作编排；[Agent Observatory](agent-observatory.md) 通过正式 runner 运行 8 种 provider-free 内置策略。自定义策略、外部模型和高级 adapter 通过 Python 的[构建 Agent](agents.md)接入；公开浏览器服务不会接受任意代码或 provider 凭据。

跨 Track 比较时，应当把操作数、测量、失败、生命周期完成度和方法资源与任务结果一起报告。
