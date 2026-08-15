# ChemWorld

[English](README.md) | **简体中文**

![ChemWorld — Agent 在可回放的实验生命周期中行动](docs/assets/chemworld-hero.png)

**面向学生、实验 Agent 与可复现研究的可编程虚拟化学实验室。**

ChemWorld 把化学任务转化为有状态、有类型的实验室：每个被接受的操作都会改变同一套虚拟装置，
仪器提供公开信号，资源使用被完整记账，整条轨迹可以回放。它是软件实验环境，**不是真实化学实验指南**。

[从 Colab 运行第一个实验](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb)
· [浏览全部 Notebook](https://github.com/Knitua/ChemWorld-Public/tree/main/notebooks)
· [打开中文文档](https://knitua.github.io/ChemWorld-Public/zh/)
· [打开在线 Student Lab](https://chemworld-public-lab.onrender.com/student/)

## 选择你的入口

| 我想要…… | 从这里开始 | 实际运行的内容 |
| --- | --- | --- |
| 完成一个引导实验 | [在 Colab 中打开 Notebook 01](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb) | 确定性“反应到终检”实验，无需 Provider Key |
| 继续完成纯化 | [在 Colab 中打开 Notebook 02](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/02_reaction_to_purification.ipynb) | 反应、萃取、洗涤、干燥与浓缩 |
| 只改变一个世界组件 | [在 Colab 中打开 Notebook 03](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/03_controlled_world_change.ipynb) | 在受控 world fork 中施加同一公开干预 |
| 手动操作虚拟实验装置 | [打开在线 Student Lab](https://chemworld-public-lab.onrender.com/student/) | 在动画工作台中运行真实的公开 Gym Runtime |
| 观察并比较 Agent | [打开在线 Agent Observatory](https://chemworld-public-lab.onrender.com/agent/) | 无需 Provider 的脚本、随机、DOE 与贝叶斯策略 |
| 接入自己的 Agent | [Agent 接入指南](https://knitua.github.io/ChemWorld-Public/zh/agents/) | 小型 Python Agent 协议与可审计轨迹 |

## 在线实验室

Student Lab 和 Agent Observatory 不是静态界面样稿。它们会创建真实的内存内 ChemWorld Gym Session，
并执行与 Python Agent 完全相同的公开动作、观测、校验、资源和回放合同。

[打开公网 Student Lab](https://chemworld-public-lab.onrender.com/student/) ·
[打开 Agent Observatory](https://chemworld-public-lab.onrender.com/agent/)

免费公网预览在闲置后可能需要短暂唤醒。如果希望运行私有本地实例：

```bash
git clone https://github.com/Knitua/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e .
chemworld lab
```

打开 `http://127.0.0.1:8876/student/` 操作实验装置，或打开
`http://127.0.0.1:8876/agent/` 单步执行并比较 provider-free 策略。出于安全设计，默认本地命令只绑定
loopback。可部署的公网服务使用独立、显式受限的模式，因此在线访客无法启用 Provider 或提交任意代码。

[Student Lab 指南](https://knitua.github.io/ChemWorld-Public/zh/student-lab/) ·
[Agent Observatory 指南](https://knitua.github.io/ChemWorld-Public/zh/agent-observatory/) ·
[部署指南](https://knitua.github.io/ChemWorld-Public/zh/deployment/)

## 公开内容

- 15 个有类型实验任务，覆盖反应、分离、结晶、蒸馏、流动化学、电化学、表征、优化与规划。
- 有状态的材料、装置和资源账本，并支持原子化校验与可恢复失败。
- 公开仪器与谱图、终检、显式终止机制，以及事务完整的轨迹。
- 8 种可在浏览器中观察的 provider-free 策略，包括脚本化学、随机与拉丁超立方设计、贪心搜索、高斯过程 BO、
  安全约束 BO 与离线 LLM-style Replay。
- 3 个保留执行输出的教程 Notebook；其结果是确定性演示，不代表 Benchmark 结论或优化后的真实实验流程。

## 安装与接入

ChemWorld 支持 Python 3.11 和 3.12。

```bash
python -m pip install -e ".[notebooks]"
python examples/demo_manual_event_sequence.py
```

Agent 可以实现小型 `BaseAgent` 协议，并通过 `run_agent` 运行。在线 Provider Adapter 是可选的 Python 工作流；
出于安全原因，它们不会暴露在公开 Lab 服务中。离线、DeepSeek 和 Codex Subscription 示例及其 Provenance 要求见
[Agent 指南](https://knitua.github.io/ChemWorld-Public/zh/agents/)。

## 可复现性与范围

`v0.4.0` 版本把 provider-free Student Lab 和 Agent Observatory 纳入稳定公开运行时。软件、Schema、测试、
Protocol、净化证据和确定性发布清单仍保留在本仓库中，以确保友好的体验入口不会取代科学审计。

- [中文文档](https://knitua.github.io/ChemWorld-Public/zh/)
- [证据地图](evidence/README.md)
- [公开 Protocol](protocols/README.md)
- [发布清单](release/manifest.json)
- [局限性与科学边界](https://knitua.github.io/ChemWorld-Public/zh/limitations/)

ChemWorld 使用 [MIT License](LICENSE) 发布。如果在研究中使用冻结版本，请引用 [`CITATION.cff`](CITATION.cff)
中的仓库元数据，并在适用时记录发布标签、任务、World Split、Seed、Action Trace 与 Provider Provenance。
