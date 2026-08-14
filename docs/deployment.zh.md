# 部署无需 Provider 的公开实验室

可部署服务在同一个 Python 进程中提供 Student Lab、Agent Observatory 和 JSON API。它执行真实
的公开 ChemWorld Gym 运行时，但明确排除在线 Provider、任意代码上传和私有评测资产。

## 本地安全仍是默认值

`chemworld lab` 仍只绑定 `127.0.0.1`。只有显式增加 `--public` 后，服务才接受非 loopback 地址。
公开模式同时启用 Session 与 Agent Run 容量上限、过期回收、并发控制、POST 限流、请求体上限和
安全响应头。

```bash
chemworld lab --public --host 0.0.0.0 --port 10000 --no-browser
```

不要向这个进程配置 Provider 凭据。公网策略目录只包含仓库内经过检查的 provider-free 白名单。

## 运行生产镜像

```bash
docker build -t chemworld-public-lab .
docker run --rm -p 10000:10000 chemworld-public-lab
```

先检查 `http://127.0.0.1:10000/api/health`，再打开 `/student/` 或 `/agent/`。容器使用非特权用户，
Session 只保存在内存中；重启后主动丢弃。

## Render 预览

仓库中的 `render.yaml` 已定义 provider-free Web Service 和健康检查：

[部署到 Render](https://render.com/deploy?repo=https://github.com/Knitua/ChemWorld-Public){ .md-button .md-button--primary }

Render 免费预览实例会在闲置后休眠，文件系统也是临时的，适合无状态演示但不代表持续在线承诺。正式
对外宣布前应升级付费实例，或迁移到其他托管容器平台。

## 默认公开限制

| 边界 | 默认值 |
| --- | ---: |
| 保留的 Student Lab Session | 64 |
| 保留的 Agent Run | 64 |
| 并发 Agent Worker | 4 |
| Session 与未访问 Run 的过期时间 | 30 分钟 |
| 每个客户端的状态修改请求 | 90/分钟 |
| JSON 请求体 | 64 KiB |

除请求体硬上限外，其余值都可通过对应 CLI 参数收紧。这些控制用于保护公开演示，并不允许用户上传
任意代码或把单进程服务当作多租户执行平台。
