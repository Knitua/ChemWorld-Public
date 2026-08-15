# Student Lab

Student Lab 是用于体验 ChemWorld 公开动作合同的动画实验台。它不会调用 Agent 或模型。

[打开公网 Student Lab](https://chemworld-public-lab.onrender.com/student/){ .md-button .md-button--primary }
[打开 Agent Observatory](https://chemworld-public-lab.onrender.com/agent/){ .md-button }

免费预览实例闲置后可能需要短暂唤醒。如需在私有本地进程中运行同一实验台，安装包后执行：

```bash
chemworld lab
```

命令会打开 `http://127.0.0.1:8876/student/`。远程机器可使用 `--no-browser`，也可用 `--port`
更换本机端口。默认命令拒绝非 loopback 的监听地址；显式受限的公开模式与本地流程保持隔离。

通过页头的模式切换可直接打开无需 Provider 的 [Agent Observatory](agent-observatory.md)，无需
重启服务。

需要托管公网预览时，请使用[部署指南](deployment.md)中的独立受限模式；默认本地命令仍只允许
loopback。

## 动画表达什么

容器动画响应已经提交的公开操作，例如投料、加热、取样、分相和结晶。标签与增量来自正常的
事务回执。动画**不会**展示或估计隐藏组成、动力学参数或评测器状态。

操作编排器根据当前步骤的 `available_actions()` 和公开 action schema 动态生成。每个 JSON
请求先通过 `validate_action()`，再交给 `step()`。被拒绝的动作不会改变物理状态或操作预算。

## 建议的第一次体验

1. 选择 **投料到最终检测**，创建 seed 0。
2. 依次加入溶剂、试剂和催化剂。
3. 加热反应并进行一次中间测量。
4. 淬灭或终止后，在合法时请求 `final_assay`。
5. 下载 JSON 记录，对比动作效果、成本、安全风险与终点分数。

Lab 只在内存中保存 session。托管预览会把动作发送到受限的 Render 服务，但不会调用在线
模型或 Provider；本地实例则完全留在当前机器。任一进程重启都会销毁 session；如需保留，请先下载记录。
