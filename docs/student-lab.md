# Student Lab

Student Lab is an animated workbench for learning the public ChemWorld action contract. It does not
invoke an agent or a model.

[Open the public Student Lab](https://chemworld-public-lab.onrender.com/student/){ .md-button .md-button--primary }
[Open the Agent Observatory](https://chemworld-public-lab.onrender.com/agent/){ .md-button }

The free preview may take a short time to wake after an idle period. To run the same workbench in a
private local process, install the package and run:

```bash
chemworld lab
```

The command opens `http://127.0.0.1:8876/student/`. Use `--no-browser` on a remote machine, or select a
different loopback port with `--port`. The default command rejects non-loopback bind addresses; an
explicit, bounded public mode is kept separate from this local workflow.

Use the mode switch in the header to open the provider-free [Agent Observatory](agent-observatory.md)
without restarting the server.

For a managed public preview, use the separate bounded mode described in the
[deployment guide](deployment.md). The default local command remains loopback-only.

## What the animation means

The vessel responds to committed public operations such as charging, heating, sampling, phase
handling and crystallization. The labels and deltas come from the normal transaction receipt. The
animation does **not** reveal or estimate hidden composition, kinetics or evaluator state.

The operation composer is generated from `available_actions()` and the public action schema at the
current step. Every submitted JSON object passes through `validate_action()` before `step()`. A
rejected action leaves physical state and operation budget unchanged.

## Suggested first exercise

1. Select **Reaction to Assay** and create seed 0.
2. Charge a solvent, reagent and catalyst.
3. Heat the reaction and make one intermediate measurement.
4. Quench or terminate, then request `final_assay` when it becomes legal.
5. Download the JSON notebook and compare action effects, cost, safety risk and endpoint score.

The Lab keeps sessions in memory. The hosted preview sends actions to the bounded Render service but
does not call an online model or Provider; a local instance remains entirely on that machine.
Restarting either process destroys its sessions. Download the record first if you want to retain it.
