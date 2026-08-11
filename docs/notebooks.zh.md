# 引导式 Notebook

这些 notebook 是由公开运行时执行的教程，不需要 Provider key，只保留确定性的演示输出。

## 01 · 第一个实验

阅读 Reaction-to-Assay 合同，验证每个请求，收集中间 HPLC 反馈，显式终止，并检查终检与资源账本。

[在 Colab 中打开](https://colab.research.google.com/github/sunyrain/ChemWorld-Public/blob/v0.3.0/notebooks/01_first_experiment.ipynb){ .md-button .md-button--primary }
[在 GitHub 查看](https://github.com/sunyrain/ChemWorld-Public/blob/main/notebooks/01_first_experiment.ipynb){ .md-button }

## 02 · 反应到纯化

从反应继续进入萃取、洗涤、干燥和浓缩，并保留动作验证与测量 receipt。

[在 Colab 中打开](https://colab.research.google.com/github/sunyrain/ChemWorld-Public/blob/v0.3.0/notebooks/02_reaction_to_purification.ipynb){ .md-button .md-button--primary }
[在 GitHub 查看](https://github.com/sunyrain/ChemWorld-Public/blob/main/notebooks/02_reaction_to_purification.ipynb){ .md-button }

## 03 · 受控世界变化

在父世界与子世界执行同一个公开干预，验证公开合同和动作序列不变，再比较公开响应。

[在 Colab 中打开](https://colab.research.google.com/github/sunyrain/ChemWorld-Public/blob/v0.3.0/notebooks/03_controlled_world_change.ipynb){ .md-button .md-button--primary }
[在 GitHub 查看](https://github.com/sunyrain/ChemWorld-Public/blob/main/notebooks/03_controlled_world_change.ipynb){ .md-button }

## 本地运行

```bash
python -m pip install -e ".[notebooks]"
jupyter lab
```

仓库中的输出只是演示，不是 benchmark 结果，也不代表最优性能。
