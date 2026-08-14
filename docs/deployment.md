# Deploy the provider-free Lab

The deployable Lab serves the Student Lab, Agent Observatory and JSON API from one Python process.
It executes the real public ChemWorld Gym runtime, but deliberately excludes online providers,
arbitrary code upload and private evaluation assets.

## Local safety remains the default

`chemworld lab` still binds only to `127.0.0.1`. A non-loopback address is accepted only when the
operator adds the explicit `--public` flag. Public mode also activates bounded session and agent-run
registries, expiry, concurrency limits, POST rate limiting, request-size limits and hardened response
headers.

```bash
chemworld lab --public --host 0.0.0.0 --port 10000 --no-browser
```

Do not add provider credentials to this process. The public catalog contains only the checked-in,
provider-free strategy whitelist.

## Run the production image

```bash
docker build -t chemworld-public-lab .
docker run --rm -p 10000:10000 chemworld-public-lab
```

Check `http://127.0.0.1:10000/api/health`, then open `/student/` or `/agent/`. The container runs as an
unprivileged user and stores sessions only in memory. A restart intentionally discards them.

## Render preview

The checked-in `render.yaml` defines a provider-free web service and health check. Use the repository
Blueprint to create a preview service:

[Deploy on Render](https://render.com/deploy?repo=https://github.com/Knitua/ChemWorld-Public){ .md-button .md-button--primary }

Render's free preview tier sleeps when idle and has an ephemeral filesystem. That matches this
stateless demonstration, but it is not a reliability commitment. Use a paid instance or another
managed container platform before announcing a continuously available production service.

## Default public limits

| Boundary | Default |
| --- | ---: |
| Retained Student Lab sessions | 64 |
| Retained Agent runs | 64 |
| Concurrent Agent workers | 4 |
| Session and inactive-run expiry | 30 minutes |
| State-changing requests per client | 90/minute |
| JSON request body | 64 KiB |

All values except the body-size ceiling can be tightened with the corresponding CLI flags. These
controls protect a public demonstration; they do not turn a single process into a multi-tenant
arbitrary-code execution platform.
