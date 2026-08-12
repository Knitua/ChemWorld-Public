# Student Lab

Student Lab is a local, animated workbench for learning the public ChemWorld action contract. It
does not invoke an agent or a model. Install the package and run:

```bash
chemworld lab
```

The command opens `http://127.0.0.1:8876/`. Use `--no-browser` on a remote machine, or select a
different loopback port with `--port`. The server rejects non-loopback bind addresses because it
has no authentication and is intended for local use only.

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

The Lab keeps sessions in memory and sends no data to an external service. Closing the process
destroys the sessions. Download the record before closing if you want to retain it.
