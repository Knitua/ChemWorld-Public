# 一次完整实验

实验 Agent 不只是选择一个终点答案。它需要阅读任务合同、提交一系列受物理约束的请求、使用仪器、管理资源，并判断何时结束实验生命周期。

## 探索冻结的 15 步轨迹

下面的控件由净化后的 `agent-instrument-use` 报告生成。可以使用鼠标、触屏或方向键选择步骤。

<div class="cw-explorer" data-cw-explorer data-locale="zh" data-source="../../assets/data/representative-behavior-and-forks.json">
  <div class="cw-explorer-header">
    <h3>一个持续 Agent，一条完整生命周期</h3>
    <div data-cw-summary>正在加载冻结公开证据…</div>
  </div>
  <div class="cw-step-strip" data-cw-step-strip role="list" aria-label="已提交的实验动作"></div>
  <div class="cw-step-detail" data-cw-step-detail aria-live="polite"></div>
</div>

<noscript><p class="cw-noscript">JavaScript 已关闭。完整静态动作与观测表仍可在下方打开。</p></noscript>

## 每一步之后发生了什么？

系统始终把三类记录分开：

1. **事务状态：** 请求是成功提交还是被回滚。
2. **公开观测：** 面向仪器的 Agent 被允许看到什么。
3. **资源结果：** 过程时间、样品消耗及注册后果。

这样，最终得分就不会抹掉实验结果是如何产生的。

## 失败仍是科学记录的一部分

确定性恢复案例会在物理前置条件不成立时故意请求相分离。操作回滚物理、随机数和 ghost 状态，保留声明的尝试后果，然后继续合法恢复。精确回放时，这次提交失败也不会被删除。

## 相同实验，不同世界

实验设计者可以构建一对受控世界：公开任务、动作 schema、资源和动作序列保持一致，只改变一个注册的私有组件。Agent 必须根据公开反馈判断，而不能直接读取组件身份。

[打开完整静态轨迹、回滚和 world fork 表](representative-behavior.md){ .md-button }

!!! note "解释边界"
    这条轨迹只证明接口可用且执行可审计，不代表 Agent 更优。World fork 只验证注册的软件模型干预，不代表真实实验室迁移。
