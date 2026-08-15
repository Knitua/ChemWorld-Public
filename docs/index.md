<section class="cw-launch-hero">
  <div class="cw-launch-copy">
    <p class="cw-eyebrow">PUBLIC v0.4 · BUILT AT TSINGHUA UNIVERSITY</p>
    <h1>Give experimental intelligence a world to act in.</h1>
    <p class="cw-lead">ChemWorld is a programmable virtual chemistry laboratory where agents choose evidence, operate typed apparatus, recover from failure and leave an exactly replayable trace.</p>
    <div class="cw-button-row">
      <a class="cw-button cw-button-primary" href="https://chemworld-public-lab.onrender.com/student/">Open the live Lab →</a>
      <a class="cw-button" href="https://chemworld-public-lab.onrender.com/agent/">Watch agents</a>
      <a class="cw-button" href="vision/">Read the thesis</a>
    </div>
  </div>
  <a class="cw-launch-visual" href="https://chemworld-public-lab.onrender.com/student/" aria-label="Open the live Student Lab">
    <img src="assets/readme/chemworld-launch-hero.png" alt="A conceptual programmable chemistry laboratory connected by an auditable agent loop">
  </a>
</section>

## The research question

Language models can describe an experiment. But can an agent decide what remains unknown, acquire the right evidence, operate under constraints, revise a failing plan and finish the experimental lifecycle? ChemWorld makes that question executable.

| Static benchmark | Interactive chemical world |
| --- | --- |
| A fixed prompt contains the evidence. | Measurements are actions with cost, time and sample consequences. |
| Correctness is judged at one output. | Every legal and invalid operation changes—or deliberately does not change—the trajectory. |
| New examples test input generalization. | Controlled world forks test whether strategy adapts when causal rules change. |

## One system, three layers

<div class="cw-grid">
  <div class="cw-card"><span class="cw-card-index">01</span><h3>Physical causal world</h3><p>Typed state, hidden dynamics, equipment, instruments and controlled interventions.</p></div>
  <div class="cw-card"><span class="cw-card-index">02</span><h3>Experimental runtime</h3><p>Validation, transactions, measurements, failures, resources, lifecycle and replay.</p></div>
  <div class="cw-card"><span class="cw-card-index">03</span><h3>Task and evaluation</h3><p>Public goals, permissions, budgets, termination and task-specific outcomes.</p></div>
</div>

## What is verified in Public v0.4

<div class="cw-proof-grid cw-proof-grid-five">
  <div class="cw-proof"><strong>64 / 64</strong><span>reference task–world units</span></div>
  <div class="cw-proof"><strong>52 / 52</strong><span>generated compositions</span></div>
  <div class="cw-proof"><strong>8 / 8</strong><span>deterministic cases</span></div>
  <div class="cw-proof"><strong>6 pairs</strong><span>24 controlled-fork traces</span></div>
  <div class="cw-proof"><strong>1 / 1</strong><span>complete agent lifecycle</span></div>
</div>

These are finite software-model qualification results. They establish the published contracts and replay boundary; they do not establish an Agent ranking, universal chemical fidelity or physical-laboratory transfer. [Inspect the evidence →](evidence.md)

## Choose a path

| Goal | Start here |
| --- | --- |
| Operate a task in the browser | [Live Student Lab](student-lab.md) |
| Step through built-in policies | [Agent Observatory](agent-observatory.md) |
| Understand the research thesis | [Why ChemWorld](vision.md) |
| See how hidden causal rules change | [Causal Worlds](causal-worlds.md) |
| Connect your own policy or model | [Build an Agent](agents.md) |
| Design a reproducible comparison | [Benchmark Design](benchmark-design.md) |

Development-frontier features and unpublished evidence remain in the [ChemWorld development repository](https://github.com/sunyrain/ChemWorld); this site documents only the stable public release.
