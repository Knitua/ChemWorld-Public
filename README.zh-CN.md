<div align="center">

[English](README.md) · **简体中文**

<sub><strong>来自清华大学的研究团队 🇨🇳</strong></sub>

# 我们不只是在设想一座虚拟化学实验室。<br>我们真正把它搭了出来——Agent 可以在里面做实验。🧪

Agent 可以行动、观测、失败、恢复，而每一个被接受的步骤都能被精确回放。

[![打开在线 ChemWorld Student Lab](docs/assets/readme/chemworld-launch-hero.png)](https://chemworld-public-lab.onrender.com/student/)

[**🚀 体验在线 Lab**](https://chemworld-public-lab.onrender.com/student/) · [**🤖 观察 Agent**](https://chemworld-public-lab.onrender.com/agent/) · [**📓 在 Colab 运行**](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb) · [**📚 阅读研究文档**](https://knitua.github.io/ChemWorld-Public/zh/)

</div>

## 一次实验：从行动到终检

![Public v0.4 确定性会话依次执行合法动作、获得公开观测并保留精确回放](docs/assets/readme/lab-lifecycle.gif)

这段 7.2 秒循环动画由冻结的 Public v0.4 生命周期生成，不是摆拍的 UI 录像。它覆盖合法加料、过程操作、仪器观测、终止与 final assay，全程只展示公开状态。

## 🔬 我们真正做成了什么

| 可编程化学世界 | 完整 Agent 实验 | 受控 World Fork 与精确回放 |
| --- | --- | --- |
| 有类型任务把动力学、相态、装置、仪器、约束和预算组合为有状态世界。 | Agent 可以设计、操作、测量、失败、恢复、终止，并通过 final assay 闭合实验。 | 只改变一条已注册私有规律、保持公开合同不变，再逐步审计配对轨迹。 |

![Public v0.4 证据：15 个公开任务、52 个合格生成组合、6 对受控 fork 与 24 条轨迹，以及 8 种 provider-free 策略](docs/assets/readme/public-proof.svg)

浏览器 Observatory 可运行 8 种内置 provider-free 策略。你自己的策略或模型则通过小型 Python Agent 协议接入，其决策、工具调用、资源与来源信息都可以保留在轨迹中。

## 🌍 为什么是 ChemWorld

| 静态 Benchmark 问…… | ChemWorld 问…… |
| --- | --- |
| 模型能否回答一个固定提示？ | Agent 会主动获取什么证据？ |
| 最终答案是否正确？ | 它能否合法操作、从失败中恢复并完成实验生命周期？ |
| 性能能否泛化到新样本？ | 当世界的因果规律受控改变时，策略还能否适应？ |

![Student Lab、Agent Observatory 与 Programmable Worlds 是同一公开运行时的三个入口](docs/assets/readme/chemworld-three-ways.svg)

## 📚 探索研究

| 目标 | 页面 |
| --- | --- |
| 理解研究主张 | [为什么是 ChemWorld](https://knitua.github.io/ChemWorld-Public/zh/vision/) |
| 阅读规范系统模型 | [系统模型](https://knitua.github.io/ChemWorld-Public/zh/architecture/) |
| 了解因果世界如何变化 | [因果世界](https://knitua.github.io/ChemWorld-Public/zh/causal-worlds/) |
| 探索 Showcase Worlds | [世界](https://knitua.github.io/ChemWorld-Public/zh/worlds/) |
| 检查 Confirmatory Benchmark Tasks | [确认性任务](https://knitua.github.io/ChemWorld-Public/zh/confirmatory-tasks/) |
| 选择 Agent 交互层级 | [Agent Tracks](https://knitua.github.io/ChemWorld-Public/zh/agent-tracks/) |
| 构建 Agent | [开始接入](https://knitua.github.io/ChemWorld-Public/zh/getting-started/) |
| 设计评估 | [Benchmark 设计](https://knitua.github.io/ChemWorld-Public/zh/benchmark-design/) |
| 理解真实世界路线图 | [真实世界桥接](https://knitua.github.io/ChemWorld-Public/zh/real-world-bridge/) |

## 本地运行

```bash
git clone https://github.com/Knitua/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e .
chemworld lab
```

随后打开 `http://127.0.0.1:8876/student/`。支持 Python 3.11 和 3.12。

## 团队、引用与边界

ChemWorld 由清华大学化工系的 **Jiangjie Qiu、Yijun Li 和 Xiaonan Wang** 共同开发。完整单位为：北京人工智能驱动的化工材料重点实验室、化学工程与低碳技术全国重点实验室、清华大学化学工程系。

引用时请使用 [`CITATION.cff`](CITATION.cff) 中的机器可读元数据，并在适用时记录版本标签、任务、world split、seed、轨迹与 provider provenance。代码采用 [MIT License](LICENSE)。

**科学边界。** ChemWorld 是用于实验交互研究的有边界软件模型环境。虚拟数值、策略与排名不构成真实实验室操作指南、经验证的化学建议，也不证明真实世界迁移。
