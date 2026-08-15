# ChemWorld

**English** | [简体中文](README.zh-CN.md)

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

## Project status

This repository contains the stable public release. Ongoing work and candidate features remain in the development repository until they are ready to publish. For reproducible studies, record the release tag, task, world split, seed and action trace.

ChemWorld is a software environment for studying experimental interaction. Its simulated quantities and policies are not instructions for physical laboratory work, and results in ChemWorld do not by themselves establish transfer to a real laboratory.

## Team and citation

ChemWorld is developed by **Jiangjie Qiu, Yijun Li and Xiaonan Wang** at the Beijing Key Laboratory of Artificial Intelligence for Advanced Chemical Engineering Materials, State Key Laboratory of Chemical Engineering and Low-Carbon Technology, Department of Chemical Engineering, Tsinghua University.

Citation metadata is provided in [`CITATION.cff`](CITATION.cff). The code is released under the [MIT License](LICENSE).
