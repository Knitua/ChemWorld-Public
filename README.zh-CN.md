# ChemWorld

[English](README.md) | **简体中文**

[![ChemWorld 虚拟化学实验室](docs/assets/chemworld-hero.png)](https://chemworld-public-lab.onrender.com/student/)

ChemWorld 是清华大学化工系研究团队开发的可编程虚拟化学环境。我们用它研究 Agent 如何设计实验、选择测量，并根据实验过程调整下一步操作。

[**🚀 体验在线 Lab**](https://chemworld-public-lab.onrender.com/student/) · [**🤖 观察 Agent**](https://chemworld-public-lab.onrender.com/agent/) · [**📓 在 Colab 运行**](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb) · [**📚 阅读研究文档**](https://knitua.github.io/ChemWorld-Public/zh/)

## 项目简介

大多数化学 Benchmark 从固定输入开始，以一个答案或预测结束。ChemWorld 则让 Agent 在有状态的实验室中工作：加料、操作装置、测量，并决定何时结束实验。环境会检查每一步操作、记录资源消耗，并保存完整轨迹。

Public v0.4 包含 15 个实验任务、8 个不依赖模型服务的参考策略和 3 个可直接运行的 Notebook。任务定义、实验协议和版本验证证据也一并公开。网页 Lab 与 Python 包使用的是同一套公开环境。

## 本地运行

```bash
git clone https://github.com/Knitua/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e .
chemworld lab
```

打开 `http://127.0.0.1:8876/student/` 进入实验台，或打开 `http://127.0.0.1:8876/agent/` 查看 Agent。支持 Python 3.11 和 3.12。

## 四种使用方式

- [**🚀 体验在线 Lab**](https://chemworld-public-lab.onrender.com/student/)：在浏览器中选择任务、编排操作，直接观察装置状态和测量结果。
- [**🤖 观察 Agent**](https://chemworld-public-lab.onrender.com/agent/)：逐步运行内置策略，查看 Agent 在相同任务中的动作、观测和结果。
- [**📓 在 Colab 运行**](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb)：无需本地安装，打开 Notebook 即可完成第一个可复现实验。
- [**📚 阅读研究文档**](https://knitua.github.io/ChemWorld-Public/zh/)：了解 ChemWorld 的研究问题、系统设计、任务、Agent 接入和评估方法。

引用信息见 [`CITATION.cff`](https://github.com/Knitua/ChemWorld-Public/blob/main/CITATION.cff)。代码采用 [MIT License](https://github.com/Knitua/ChemWorld-Public/blob/main/LICENSE)。
