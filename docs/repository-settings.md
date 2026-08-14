# Maintainer release settings

These repository settings cannot be enforced by source code. A maintainer should apply them before
publishing v0.4.0.

- Confirm Actions workflows are enabled and able to start.
- Set **Settings → Pages → Build and deployment → Source** to **GitHub Actions**.
- Add repository description: `Programmable chemical worlds for controlled, replayable agent experimentation.`
- Set the homepage to `https://knitua.github.io/ChemWorld-Public/`.
- Add topics: `ai4science`, `chemistry`, `agent-evaluation`, `gymnasium`, `world-model`, `reinforcement-learning`.
- Require the `CI / quality` and `CI / wheel-smoke` checks on `main`.
- Create releases by pushing a version-matching tag only after CI and Documentation both pass.

The release workflow creates a GitHub Release and attaches source and Python package artifacts. PyPI
publication is deliberately not enabled until package ownership and trusted publishing are configured.
