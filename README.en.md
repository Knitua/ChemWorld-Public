# ChemWorld

[简体中文](README.md) | **English**

[![ChemWorld virtual chemistry laboratory](docs/assets/chemworld-hero.png)](https://chemworld-public-lab.onrender.com/student/)

ChemWorld is a programmable virtual chemistry environment developed by researchers in the Department of Chemical Engineering at Tsinghua University. We use it to study how agents plan experiments, choose measurements and adapt their actions as an experiment unfolds.

[**🚀 Try the Live Lab**](https://chemworld-public-lab.onrender.com/student/) · [**🤖 Watch Agents**](https://chemworld-public-lab.onrender.com/agent/) · [**📓 Run in Colab**](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb) · [**📚 Read the Documentation**](https://knitua.github.io/ChemWorld-Public/)

## About

Most chemistry benchmarks begin with a fixed input and end with an answer or prediction. In ChemWorld, an agent works inside a stateful laboratory. It adds materials, operates apparatus, takes measurements and decides when an experiment is complete. The environment checks each operation, accounts for resources and records the resulting trace.

Public v0.4 contains 15 experimental tasks, eight provider-free reference policies and three executable notebooks. It also includes the task definitions, protocols and evidence used to check the release. The browser Lab and the Python package run the same public environment.

## Run locally

```bash
git clone https://github.com/Knitua/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e .
chemworld lab
```

Open `http://127.0.0.1:8876/student/` for the Lab or `http://127.0.0.1:8876/agent/` for the Agent view. Python 3.11 and 3.12 are supported.

## Four ways to use ChemWorld

- [**🚀 Try the Live Lab**](https://chemworld-public-lab.onrender.com/student/) — Choose a task, compose operations and see how the apparatus and measurements respond in the browser.
- [**🤖 Watch Agents**](https://chemworld-public-lab.onrender.com/agent/) — Step through the built-in policies and inspect their actions, observations and results on the same tasks.
- [**📓 Run in Colab**](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb) — Open a notebook and run a reproducible first experiment without installing ChemWorld locally.
- [**📚 Read the Documentation**](https://knitua.github.io/ChemWorld-Public/) — Read about the research question, system design, tasks, agent integration and evaluation.

Citation metadata is provided in [`CITATION.cff`](https://github.com/Knitua/ChemWorld-Public/blob/main/CITATION.cff). The code is released under the [MIT License](https://github.com/Knitua/ChemWorld-Public/blob/main/LICENSE).
