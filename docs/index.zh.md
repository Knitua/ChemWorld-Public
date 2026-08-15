<section class="cw-launch-hero">
  <div class="cw-launch-copy">
    <p class="cw-eyebrow">CHEMWORLD PUBLIC v0.4</p>
    <h1>可编程虚拟化学实验室</h1>
    <p class="cw-lead">ChemWorld 提供有状态的实验环境，用于研究 Agent 如何规划实验、操作装置、使用测量并处理失败。</p>
    <div class="cw-button-row">
      <a class="cw-button cw-button-primary" href="https://chemworld-public-lab.onrender.com/student/">打开在线 Lab →</a>
      <a class="cw-button" href="https://chemworld-public-lab.onrender.com/agent/">观察 Agent</a>
      <a class="cw-button" href="vision/">阅读研究主张</a>
    </div>
  </div>
  <a class="cw-launch-visual" href="https://chemworld-public-lab.onrender.com/student/" aria-label="打开在线 Student Lab">
    <img src="../assets/chemworld-hero.png" alt="ChemWorld 虚拟化学实验室">
  </a>
</section>

## 研究问题

语言模型可以描述实验。但 Agent 能否判断尚未知晓的部分、主动获取正确证据、在约束下操作、修正失败计划，并闭合完整实验生命周期？ChemWorld 把这个问题变成了可执行系统。

| 静态 Benchmark | 可交互化学世界 |
| --- | --- |
| 固定提示已经包含证据。 | 测量本身是动作，会消耗成本、时间或样品。 |
| 在单次输出上判断正确性。 | 每个合法或无效操作都会改变——或明确不改变——轨迹。 |
| 新样本测试输入泛化。 | 受控 world fork 测试因果规律变化后策略能否适应。 |

## 一个系统，三层合同

<div class="cw-grid">
  <div class="cw-card"><span class="cw-card-index">01</span><h3>物理因果世界</h3><p>有类型状态、隐藏动力学、装置、仪器与受控干预。</p></div>
  <div class="cw-card"><span class="cw-card-index">02</span><h3>实验交互运行时</h3><p>校验、事务、测量、失败、资源、生命周期与回放。</p></div>
  <div class="cw-card"><span class="cw-card-index">03</span><h3>任务与评估</h3><p>公开目标、权限、预算、终止规则与任务特定结果。</p></div>
</div>

## Public v0.4 已验证的内容

<div class="cw-proof-grid cw-proof-grid-five">
  <div class="cw-proof"><strong>64 / 64</strong><span>参考任务–世界单元</span></div>
  <div class="cw-proof"><strong>52 / 52</strong><span>生成组合</span></div>
  <div class="cw-proof"><strong>8 / 8</strong><span>确定性用例</span></div>
  <div class="cw-proof"><strong>6 对</strong><span>24 条受控 fork 轨迹</span></div>
  <div class="cw-proof"><strong>1 / 1</strong><span>完整 Agent 生命周期</span></div>
</div>

这些是有限的软件模型资格结果，用来建立已发布合同与回放边界；它们不建立 Agent 排名、普适化学保真度或真实实验室迁移结论。[检查证据 →](evidence.md)

## 选择一条路径

| 目标 | 从这里开始 |
| --- | --- |
| 在浏览器中操作任务 | [在线 Student Lab](student-lab.md) |
| 逐步观察内置策略 | [Agent Observatory](agent-observatory.md) |
| 理解研究主张 | [为什么是 ChemWorld](vision.md) |
| 了解隐藏因果规则如何变化 | [因果世界](causal-worlds.md) |
| 接入自己的策略或模型 | [构建 Agent](agents.md) |
| 设计可复现比较 | [Benchmark 设计](benchmark-design.md) |

开发前沿功能与未发布证据仍留在 [ChemWorld 开发仓库](https://github.com/sunyrain/ChemWorld)；本网站只描述稳定公开版本。
