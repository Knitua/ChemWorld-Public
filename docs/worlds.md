# Showcase Worlds

ChemWorld presents a family of interoperable experimental worlds rather than fifteen isolated simulators. Tasks select different slices of one typed operation language and compose the apparatus, material, instrument and scoring capabilities they need.

## World families

| Family | Public tasks and questions |
| --- | --- |
| Reaction and assay | `reaction-to-assay`, standard optimization, safety-constrained optimization, mechanism explanation |
| Separation and purification | partition discovery, reaction-to-purification, purity–yield trade-off |
| Crystallization | seeded cooling, isolation, purity, yield and particle-size trade-offs |
| Distillation | volatile-product recovery after reaction |
| Flow | geometry-resolved PFR optimization under bounded process controls |
| Electrochemistry | solvent/electrolyte choice and selective charge- and energy-efficient conversion |
| Characterization and planning | equilibrium characterization, low-budget characterization and tool-agent planning |

The registered Public v0.4 task census is 15. “Showcase” means platform breadth and teaching value; it does not grant every task a formal Agent-comparison claim.

## Shared experimental language

Depending on the task, the same runtime can expose:

- material operations such as adding solvents, reagents, catalysts, phases or extractants;
- process operations such as heat, mix, settle, crystallize, distill, run flow or electrolyze;
- workup operations such as separate, wash, dry, evaporate and collect;
- public instruments such as HPLC, GC, spectroscopy, voltammetry and final assay;
- lifecycle operations including termination and contract-valid closeout.

`available_actions()` and the action schemas are state-dependent. A world is not a menu of always-valid buttons: apparatus, materials, task permissions and budget determine what can commit next.

## Composition qualification

The release qualifies 64 reference task–world units and 52 generated compositions. Qualification checks interface compatibility, deterministic replay, bounded response, conservation and task-level execution. These counts are coverage evidence for the software composition system, not 116 independent chemical validations.

Explore the [world capability map](world-capability-map.md), [composition examples](world-composition-examples.md), or operate them in the [Student Lab](student-lab.md).
