# LiteLLM Version Policy

Anticipated by D-002; automation and enforcement landed with D-015.

## Why litellm is pinned

InferenceGate's enforcement path depends on litellm-**internal** behavior
that changes without notice between minor versions:

- **Hook dispatch**: guardrails route through `apply_guardrail` only when it
  appears in `type(callback).__dict__` — a change here can silently stop
  shields from running at all (this exact failure occurred and was caught
  by the integration suite; see WORKLOG 2026-07-15).
- **Registry layout**: the management-UI integration registers providers in
  `guardrail_class_registry` / `guardrail_initializer_registry` (D-013).
- **Exception conventions**: blocks raise `fastapi.HTTPException(400)`, the
  form litellm records as a guardrail intervention (D-012).

An unpinned litellm therefore means untested *security* behavior, and
fail-open defaults mean a regression may not be visible. The pin also makes
supply-chain changes deliberate: `uv.lock` carries hashes.

## Where the pin lives

| Layer | Mechanism | Value |
|-------|-----------|-------|
| Reference deployment | `pyproject.toml` → `[tool.uv].constraint-dependencies` + `uv.lock` | exactly `litellm==<tested>` |
| pip package (BYO) | package metadata | open range `litellm>=1.82.0` (an exact pin would conflict with the consumer's proxy) |
| Runtime | `TESTED_LITELLM_VERSION` in `inference_gate/shields.py` | startup **warning** when the running litellm differs |

A unit test (`TestLitellmVersionPolicy`) asserts the constraint, the
installed version, and `TESTED_LITELLM_VERSION` agree — drift fails CI.

## How upgrades happen

1. **Automated proposal**: the `litellm-bump` workflow (weekly, or manual
   via *Actions → litellm bump → Run workflow*) checks PyPI, applies the
   bump on a branch (`pyproject.toml`, `uv.lock`,
   `TESTED_LITELLM_VERSION`, README, Docker guide), runs the full unit +
   live-proxy integration battery against the new version, and opens a PR
   titled with the battery verdict. The battery runs inside the workflow
   because `GITHUB_TOKEN`-created PRs do not trigger the Tests workflow;
   close/reopen the PR to force a normal CI run.
2. **Human review**: merge only battery-PASSED proposals. A FAILED
   proposal is a signal, not noise — it documents which litellm version
   breaks which shield behavior; investigate before litellm's version
   ages out.
3. **Security releases**: if litellm ships a security fix, don't wait for
   Monday — trigger the workflow manually and prioritize the merge. A
   firewall on a proxy with a known CVE is worse than a briefly-warned
   untested version.

Routine (non-litellm) dependency updates are handled by Dependabot
(`.github/dependabot.yml`), which explicitly ignores litellm.

## BYO consumers

Users installing the `inference-gate` package into their own proxy get the
open range plus the startup warning when their litellm differs from the
tested version. The credential-free compatibility battery is public: clone
this repo and run `uv run pytest tests/ -m integration -q` against any
litellm version in minutes.
