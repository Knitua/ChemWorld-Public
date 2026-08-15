# 快速开始

根据你想了解的内容，选择最短入口。

## 无需安装，直接体验

- [打开在线 Student Lab](https://chemworld-public-lab.onrender.com/student/)，选择任务并编排合法操作。
- [打开 Agent Observatory](https://chemworld-public-lab.onrender.com/agent/)，逐步观察 8 种 provider-free 策略。
- [在 Colab 运行第一个实验](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb)，查看保留输出的确定性流程。

免费的 Render 服务在闲置后可能需要短暂唤醒。

## 本地运行

```bash
git clone https://github.com/Knitua/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e .
chemworld lab
```

打开 `http://127.0.0.1:8876/student/` 或 `http://127.0.0.1:8876/agent/`。默认服务只绑定 loopback。

## 运行一次 Agent Episode

```bash
chemworld tasks list
chemworld run --task reaction-to-assay --agent scripted_chemistry --seed 0
```

命令会在 `runs/` 下写入轨迹和 manifest。使用终端打印的轨迹路径进行验证和评估：

```bash
chemworld verify --constitution --submission runs/<trajectory>.jsonl
chemworld evaluate --submission runs/<trajectory>.jsonl
```

## 编写自己的 Agent

实现小型 `BaseAgent` 协议，并把实例传给 `run_agent`。完整示例见[构建 Agent](agents.md)。Provider adapter 是可选 Python 工作流；公开 Lab 始终保持 provider-free，也不会接受访客任意代码。

## 理解合同

通过[一次完整实验](one-experiment.md)理解生命周期，通过[系统模型](architecture.md)理解所有权边界，通过 [API 参考](reference.md)了解运行时表面。更细的逐命令教程仍保留在历史兼容页[安装指南](getting_started.md)。
