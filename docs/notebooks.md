# Guided notebooks

The notebooks are executable tutorials generated from the public runtime. They require no provider key and retain only deterministic demonstration outputs.

## 01 · First experiment

Read a Reaction-to-Assay contract, validate every request, collect intermediate HPLC feedback, terminate explicitly and inspect the final assay and resource ledger.

[Open in Colab](https://colab.research.google.com/github/sunyrain/ChemWorld-Public/blob/v0.3.0/notebooks/01_first_experiment.ipynb){ .md-button .md-button--primary }
[View on GitHub](https://github.com/sunyrain/ChemWorld-Public/blob/main/notebooks/01_first_experiment.ipynb){ .md-button }

## 02 · Reaction to purification

Continue from reaction into extraction, wash, drying and concentration while keeping validation and measurement receipts visible.

[Open in Colab](https://colab.research.google.com/github/sunyrain/ChemWorld-Public/blob/v0.3.0/notebooks/02_reaction_to_purification.ipynb){ .md-button .md-button--primary }
[View on GitHub](https://github.com/sunyrain/ChemWorld-Public/blob/main/notebooks/02_reaction_to_purification.ipynb){ .md-button }

## 03 · Controlled world change

Run one public intervention in a parent and child world, verify the public contract and action sequence remain fixed, then compare the public responses.

[Open in Colab](https://colab.research.google.com/github/sunyrain/ChemWorld-Public/blob/v0.3.0/notebooks/03_controlled_world_change.ipynb){ .md-button .md-button--primary }
[View on GitHub](https://github.com/sunyrain/ChemWorld-Public/blob/main/notebooks/03_controlled_world_change.ipynb){ .md-button }

## Run locally

```bash
python -m pip install -e ".[notebooks]"
jupyter lab
```

The checked-in outputs are examples, not benchmark results or claims of optimal performance.
