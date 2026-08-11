<div class="cw-hero">
  <div class="cw-eyebrow">可编程化学世界</div>
  <h1>让 Agent 学会做实验，而不只是回答问题。</h1>
  <p class="cw-lead">ChemWorld 是一个可执行的物理化学环境：Agent 选择有类型的操作、使用仪器、消耗明确资源、面对可恢复失败，并留下能够精确回放的实验轨迹。</p>
  <div class="cw-button-row">
    <a class="cw-button cw-button-primary" href="notebooks/">运行第一个实验 →</a>
    <a class="cw-button" href="one-experiment/">查看完整 15 步</a>
    <a class="cw-button" href="evidence/">检查公开证据</a>
  </div>
  <div class="cw-pill-row">
    <span class="cw-pill">Python 3.11–3.12</span>
    <span class="cw-pill">Gymnasium API</span>
    <span class="cw-pill">演示无需 Provider</span>
    <span class="cw-pill">精确回放</span>
  </div>
</div>

## 一个接口覆盖完整实验生命周期

<div class="cw-grid">
  <div class="cw-card"><h3>操作</h3><p>阅读公开任务合同、验证操作，并提交有类型的实验动作。</p></div>
  <div class="cw-card"><h3>观测</h3><p>使用 HPLC、GC 和终检数据包，但不能直接读取评测者拥有的世界状态。</p></div>
  <div class="cw-card"><h3>学习</h3><p>比较可重复的干预，更新局部世界模型，再选择下一次信息量更高的实验。</p></div>
</div>

<div class="cw-figure-frame">
  <img src="assets/representative-agent-and-world-change.svg" alt="三个由公开证据生成的视图：15 步 Agent 生命周期、一次回滚后的恢复，以及固定公开实验下的受控世界规律变化。">
</div>

这张图由冻结公开报告确定性生成，不是手工挑选的成功故事。它同时展示完整 Agent 生命周期、保留在科学记录中的失败事务，以及相同公开实验下的受控世界变化。

## 已验证的范围

<div class="cw-proof-grid">
  <div class="cw-proof"><strong>64 / 64</strong><span>注册任务–世界单元通过资格测试</span></div>
  <div class="cw-proof"><strong>89 个动作</strong><span>覆盖八条确定性实验生命周期</span></div>
  <div class="cw-proof"><strong>6 对世界</strong><span>受控 world fork 且可精确回放</span></div>
</div>

这些是有限的软件模型资格结果，不代表普适化学保真度，也不代表能够迁移到真实实验室。

## 选择你的入口

<div class="cw-path-grid">
  <div class="cw-path-card"><h3>我想直接使用 ChemWorld</h3><p>先完成五分钟安装，再运行 Reaction-to-Assay 引导 notebook。</p><p><a href="quickstart/">打开五分钟开始 →</a></p></div>
  <div class="cw-path-card"><h3>我想理解研究基座</h3><p>了解公开合同、世界私有组件和多轮干预如何组合在一起。</p><p><a href="world-foundations/">阅读世界基座 →</a></p></div>
</div>
