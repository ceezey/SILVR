# Project Build Guide (BUILD)

> **Project memory lives in the AI Memory Vault, not in this repo.** Since 2026-10-19 every SilverBot doc (PRD, SDD, RFCs, QAD, OPS, runbooks, CRs, the LOG and the audit) is a note in the Obsidian vault at `C:\AI Agentic Memory`. Before working:
>
> 1. Read the vault rules: `C:\AI Agentic Memory\AGENTS.md`.
> 2. Read the project index, which is also the doc status manifest: `C:\AI Agentic Memory\01_Projects\SilverBot\00_Project_Index.md`.
> 3. Read prior session notes in `C:\AI Agentic Memory\01_Projects\SilverBot\Memory\`.
>
> Write project knowledge (doc updates, CRs, session logs, decisions) in the vault, never in `docs/`. The repo's [docs/index.md](docs/index.md) only points there. This file is hand-maintained and is the only copy of the build guide.

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-21
**Last reconciled:** 2026-10-21 against code at commit `c523f04` for the section 3 stack table (ccxt, the first runtime dependency); 2026-10-08 against code at commit `62037d1` for the rest; section 1 traceability, the section 3 deprecations register and golden path (b) re-checked 2026-10-09 against `70ccaec`; the D-4 and D-11 rows of the deprecations register re-checked 2026-10-09 against `099085b`

This guide tells a coding agent or a human how to build Silver Bot from the canonical docs. It is the root `AGENTS.md`, which every future session reads first. Safety rules in section 5 are carried over from the previous `AGENTS.md` and must not be weakened.

## 1. How to Build From These Docs

Read in this order. Start at the vault project index (`C:\AI Agentic Memory\01_Projects\SilverBot\00_Project_Index.md`; [docs/index.md](docs/index.md) points there), then:

```mermaid
flowchart LR
    I["Project index (vault)"] --> S["SCRUTINY"]
    S --> B["BRD"]
    B --> P["PRD"]
    P --> D["SDD"]
    D --> R["RFCs"]
    R --> Q["QAD"]
    Q --> X["AIA, CLR, OPS"]
    X --> G["BUILD (this guide)"]
```

1. [scrutiny-silverbot.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/scrutiny-silverbot.md>): gaps (`G-#`) and what is known to be wrong.
2. [brd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/brd-silverbot.md>): business goals, metrics, owner-input register.
3. [prd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/prd-silverbot.md>): features `PRD-F1`..`PRD-F12`, stories, status, task checkboxes (section 9).
4. [sdd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/sdd-silverbot.md>): architecture and module design.
5. RFCs: [signal engine](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-signal-engine.md>), [risk and kill switch](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-risk-kill-switch.md>), [ML filter gate](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-ml-filter-gate.md>), [readiness gates](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-readiness-gates.md>).
6. [qad-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/qad-silverbot.md>): test scenarios `QAD-T#`.
7. [aia-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/aia-silverbot.md>), [clr-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/clr-silverbot.md>), [ops-silverbot.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/ops-silverbot.md>): AI risks, compliance rows, runbooks.
8. This guide. Supporting: [idea-silverbot.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/idea-silverbot.md>), [val-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/val-silverbot.md>), [ues-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/ues-silverbot.md>), [sad-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/sad-silverbot.md>), [voice-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/voice-silverbot.md>), [audit-docs-drift.md](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>), [README.md](README.md).

Draft docs are the best current knowledge and the code wins over them. Flag a doc/code disagreement or an `Open` / `Owner input required` item to the owner instead of guessing. Once a doc is Locked, changes to it need a Change Record. A disagreement is recorded in [audit-docs-drift.md](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>).

Re-ground (re-read the relevant doc and the code) when:

- a task touches `risk/`, `execution/`, `exchange/`, `config/`, `readiness.py` or `demo_readiness.py`;
- a doc and the code disagree, or a doc says `Open` or `Owner input required`;
- the pinned stack in section 3 may have changed;
- more than one task has passed since you last read the index.

### Traceability map

| To build | Read | Verify against |
|----------|------|----------------|
| Signal engine (PRD-F1) | [rfc-silverbot-signal-engine.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-signal-engine.md>), SDD strategy section | `tests/` strategy tests, QAD strategy scenarios |
| Backtester and validation (PRD-F2) | SDD backtest section, [qad-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/qad-silverbot.md>) | backtest tests; evidence reports must be non-empty before any performance claim |
| Risk engine and kill switch (PRD-F3) | [rfc-silverbot-risk-kill-switch.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-risk-kill-switch.md>) | risk tests, [clr-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/clr-silverbot.md>), subagent SAD-A2 |
| Paper trading (PRD-F4) | SDD execution section | paper trading tests with mocked exchange |
| Demo mode (PRD-F5) and readiness (PRD-F8) | [rfc-silverbot-readiness-gates.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-readiness-gates.md>) | readiness tests, subagent SAD-A1 |
| ML filter (PRD-F6) | [rfc-silverbot-ml-filter-gate.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-ml-filter-gate.md>), [aia-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/aia-silverbot.md>) | ML tests, subagent SAD-A3 |
| Monitoring (PRD-F7), deployment (PRD-F11) | [ops-silverbot.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/ops-silverbot.md>) | monitoring tests, runbook steps |
| Config (PRD-F9), data and storage (PRD-F10) | SDD config and data sections | config tests, the runbook-local-dev step 3 env block loads; `.env.example` loads as paper mode since `c6d909d` (G-4 closed, `tests/test_config.py:258`) |

## 2. Subagents

Four safety reviewers run before merge on the paths each guards, and one standard-library-only builder (`psl-purist`, SAD-B1) writes operator UI and Telegram code on request. The roster, trigger rules and orchestration are in [sad-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/sad-silverbot.md>) sections 3 and 4. The agent cards live in `.claude/agents/`, are hand-maintained and canonical. The SAD section 3 holds a snapshot: after editing a card, copy the change into the SAD.

## 3. Stack Currency & Deprecations

**Verified 2026-10-21** against `pyproject.toml`, `Dockerfile` and the code at commit `c523f04`. The `ccxt` row was checked against the installed package (`ccxt.__version__` is 4.5.89) and a Docker build on the same day.

| Component | Pinned value | Source |
|-----------|--------------|--------|
| Python | `requires-python = ">=3.11"` | `pyproject.toml` |
| Runtime dependencies | `dependencies = ["ccxt>=4.5,<5"]` (one declared; everything else is standard library) | `pyproject.toml` |
| ccxt | `>=4.5,<5`; 4.5.89 installed and verified 2026-10-21. Used for public candle history through `ccxt.async_support.binanceusdm`; an API key is attached only on the Binance Futures testnet host | `pyproject.toml`; `src/silver_bot/exchange/binance_futures.py` |
| Dev dependency | `pytest>=8.0` (optional extra `dev`) | `pyproject.toml` |
| Build backend | `setuptools>=68` | `pyproject.toml` |
| scikit-learn | Optional and undeclared; used only for the RandomForest and GradientBoosting models if it imports | [aia-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/aia-silverbot.md>) section 1.2 |
| Docker base image | `python:3.11-slim` | `Dockerfile` line 1 |
| Binance Futures REST and WebSocket | Versionless public API; no pinned version | https://binance-docs.github.io/apidocs/futures/en/ |

No version in this table is invented. If `pyproject.toml` or the `Dockerfile` changes, update the table and its date.

### Deprecations register

| ID | Old convention (in old docs) | Current code | Use instead |
|----|------------------------------|--------------|-------------|
| D-4 | `ML_FILTER_ENABLED` and `ML_ENABLED` turn the ML filter on | Partly resolved (`f84557e`): the keys reach the filter in CLI backtests only (`src/silver_bot/backtest/runner.py:50-55`); the paper loop ignores them | Treat ML as not wired outside backtests; see [rfc-silverbot-ml-filter-gate.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-ml-filter-gate.md>) |
| D-11 | `MAX_RISK_PER_TRADE`, `MAX_DAILY_LOSS`, `MAX_LEVERAGE` env keys set risk caps | Partly resolved (`5e4acc5`): `MAX_RISK_PER_TRADE` must be in (0, 0.005] in every mode and `RiskConfig` rejects more than 0.005; `build_risk_config` maps all three keys and the kill-switch path into `RiskConfig` (`4726cb5`) and CLI backtests use it with a simulated per-run kill switch; nothing calls `build_risk_engine` at runtime yet (G-3), and the daily-loss and leverage bounds are checked in demo mode only | Build a runtime engine with `build_risk_engine(config, storage)` (`src/silver_bot/risk/factory.py:26-33`); a backtest takes `build_risk_config` through `build_backtest_config` (`src/silver_bot/backtest/runner.py:35-57`) and never the real kill-switch path; never hand-build a `RiskConfig` for a running bot; see [rfc-silverbot-risk-kill-switch.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-risk-kill-switch.md>) |
| D-10 | Live trading is gated by `LIVE_TRADING` plus readiness | `LIVE_TRADING=true` is rejected at load; readiness is never consulted by the entrypoint | Live is `Planned, blocked`; see [rfc-silverbot-readiness-gates.md](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-readiness-gates.md>) |

The full list is in [audit-docs-drift.md](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>).

## 4. Golden-Path Patterns

Excerpted from real code, verified 2026-10-08 against commit `62037d1`. Copy the shape, not the line numbers.

### (a) A strategy rejection returns NO_TRADE with a reason

`src/silver_bot/strategy/silver_bullet.py:67-73` and `:258-267`:

```python
        if len(candles) < max(5, self.config.swing_lookback + 3):
            return self._reject(candles, "Not enough candles to evaluate Silver Bullet setup")

        latest = candles[-1]
        session = self.sessions.evaluate(latest.open_time)
        if not session.is_active:
            return self._reject(candles, "Outside enabled Silver Bullet session")
...
    def _reject(self, candles: Sequence[Candle], reason: str) -> SilverBulletSignal:
        latest = candles[-1] if candles else None
        return SilverBulletSignal(
            direction=SignalDirection.NO_TRADE,
            symbol=latest.symbol if latest else "UNKNOWN",
            timeframe=latest.timeframe if latest else "UNKNOWN",
            generated_at=self._signal_timestamp(latest) if latest else datetime.now(timezone.utc),
            reason=reason,
            explanation=f"NO_TRADE: {reason}",
        )
```

`strategy/models.py:191-192` enforces it: a `NO_TRADE` signal without a reason raises `ValueError`.

### (b) An order request passes through the risk engine and kill switch

`src/silver_bot/risk/engine.py:38-55` (an unreadable persisted risk state halts first; the kill switch is the first gate) and `src/silver_bot/execution/paper_trading.py:207-216` (the caller must ask the risk engine before any fill):

```python
    def evaluate(self, request: RiskRequest) -> RiskDecision:
        """Return a risk decision with an explicit approval or rejection reason."""

        if self.state_load_error is not None:
            return self._reject("Risk state could not be loaded; trading halted")
        previous_day = self.state.current_day
        self.state.roll_day(request.signal_day)
        if self.state.current_day != previous_day:
            self._save_state()

        if self.kill_switch.is_active():
            return self._reject("Kill switch is active")
        if request.equity <= 0:
            return self._reject("Account equity must be positive")
        if request.entry_price is None:
            return self._reject("Entry price is required")
        if request.stop_loss is None:
            return self._reject("Stop loss is required")
```

```python
        decision = self.risk.evaluate(
            RiskRequest(
                equity=self.equity,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                direction=signal.direction.value,
                signal_day=signal.generated_at.date(),
            )
        )
        if not decision.approved:
            ...
            return
```

The `...` elides the lines after line 217 (the `if not decision.approved:` header; the rejection event, audit log and alert).

A rejected decision is recorded and the function returns before any position is opened.

### (c) Fail-closed config validation rejects live mode

`src/silver_bot/config/settings.py:105-108`:

```python
    if live_trading:
        raise ConfigError("LIVE_TRADING=true is rejected in Phase 1")
    if raw.get("TRADING_MODE", "").strip().lower() == "live":
        raise ConfigError("TRADING_MODE=live is not supported in Phase 1")
```

Any new mode or flag must follow the same rule: invalid or unsafe input raises `ConfigError`; it never degrades to a permissive default.

## 5. Conventions & Guardrails

### Non-Negotiable Safety Rules

Never:

```text
enable live trading by default
place real orders unless LIVE_TRADING=true
hardcode API keys
commit .env files
use martingale
average down
trade without stop loss
let ML generate trades directly
bypass the risk engine
bypass the kill switch
optimize on the final test set
```

### Default Mode

Default mode must be:

```text
paper or backtest
```

Live trading must be blocked unless explicitly enabled and readiness checks pass.

### Development Style

Use:

```text
Python 3.11+
type hints
docstrings
modular files
pytest tests
clear error handling
structured logging
```

Prefer simple, understandable code over clever code.

### Expected Repository Layout

Use this structure unless there is a strong reason to change it:

```text
src/silver_bot/
  config/
  data/
  exchange/
  strategy/
  risk/
  execution/
  backtest/
  ml/
  monitoring/
  storage/
  utils/

tests/
data/
models/
logs/
reports/
```

### Implementation Rules

The bot must be developed phase by phase. Do not attempt to build the entire roadmap in one pass.

For every task:

1. Read the relevant documentation.
2. Implement only the requested phase or task.
3. Add or update tests.
4. Do not introduce live trading unless explicitly requested.
5. Update `PROGRESS.md`.
6. Update `TODO.md` checkboxes if tasks are completed.
7. Summarize changed files.
8. Explain how to run tests.

Note: `PROGRESS.md` and `TODO.md` were retired by the documentation suite. Read steps 5 and 6 as: update the vault project index (`01_Projects/SilverBot/00_Project_Index.md`) and the LOG ([log-silverbot](<C:/AI Agentic Memory/01_Projects/SilverBot/Logs/log-silverbot.md>)), and update the PRD section 9 checkboxes.

### Strategy Rules

The strategy is ICT Silver Bullet.

The bot should look for:

```text
session window
liquidity sweep
displacement
market structure shift
Fair Value Gap
retracement into FVG
defined stop loss
liquidity-based take profit
```

The strategy engine should output:

```text
LONG
SHORT
NO_TRADE
```

Every rejected setup must include a reason.

### ML Rules

ML is optional.

ML can only:

```text
approve a rule-based signal
reject a rule-based signal
reduce risk
```

ML cannot:

```text
generate trades
place orders
increase risk beyond maximum
bypass stop loss
bypass kill switch
```

### Risk Rules

The risk engine is mandatory.

Every trade must pass:

```text
position sizing
stop-loss validation
reward-to-risk validation
daily loss validation
consecutive loss validation
max trades validation
kill switch validation
```

### Testing Requirements

When adding code, add tests for:

```text
normal cases
edge cases
unsafe cases
invalid config
risk rejection
```

Use mocks for exchange calls.

Do not require real API keys for tests.

### Documentation Updates

When completing a task:

- update the vault project index (`C:\AI Agentic Memory\01_Projects\SilverBot\00_Project_Index.md`) and the LOG ([log-silverbot](<C:/AI Agentic Memory/01_Projects/SilverBot/Logs/log-silverbot.md>)) every task;
- update the PRD section 9 checkboxes ([prd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/prd-silverbot.md>));
- if architecture, strategy, risk or ML changes, update the SDD, RFC-001 (signal engine), RFC-002 (risk and kill switch) or the AIA respectively;
- a change to a Locked doc requires a Change Record (section 5.1);
- doc edits happen in the vault, follow its frontmatter and wikilink rules (vault `AGENTS.md` sections 3 and 4), and never rename a note (repo code cites `runbook-backtest.md` and `runbook-demo-testnet.md` by basename).

### Diagrams

Every diagram in the docs is a fenced `mermaid` block (flowchart, sequenceDiagram, stateDiagram-v2 or erDiagram) so it renders in Obsidian and on GitHub. Validate with `npx -y @mermaid-js/mermaid-cli@11.4.2` run in a scratch directory outside the repo.

### Restraint ladder

Add only what the task needs. Climb one rung at a time:

1. Do nothing: the existing code or doc already answers it.
2. Reuse: call or extend what exists.
3. Configure: change a value, not code.
4. Add the smallest new function or doc paragraph.
5. Add a new module or doc only when rungs 1 to 4 fail.

Never cut: validation, risk gates, the kill switch, stop loss, tests or secret hygiene. YAGNI applies to features, not to safety.

### 5.1 Change Workflow

1. When a change touches a Locked doc, propose a Change Record `cr-silverbot-<slug>.md` in the vault folder `01_Projects/SilverBot/Change_Records/` (template `03_Resources/Templates/change-record-template.md`) with sections: Why, Divergences, Changes, Verification, Pre-merge gate runs, Deferred.
2. Apply the change (code, tests, docs).
3. Verify: run the tests and the doc checks; run the subagent reviewers that SAD section 4 requires.
4. Register the Change Record in section 2 of the vault project index.

### Definition of Done

- Tests added and passing (`python -m pytest`); no real API key needed.
- No safety rule in section 5 weakened; risk engine and kill switch still on every order path.
- Docs updated per "Documentation Updates"; no em dashes; links resolve.
- Required subagent reviewers returned PASS or the owner recorded why a FAIL is accepted.
- Final response given in the format below.

### Code review checklist

- [ ] Any path to a real order without the risk engine, kill switch or stop loss?
- [ ] Any default that is permissive (live, ML, kill switch off)?
- [ ] Any secret, `.env` content or API key in code, tests or logs?
- [ ] Any lookahead or leakage, or use of the final test set for tuning?
- [ ] Every rejected setup carries a reason?
- [ ] Tests cover normal, edge, unsafe, invalid config and risk rejection?
- [ ] Performance claims backed by a non-empty evidence report?

### Final Response After Each Task

After completing a task, provide:

```text
Summary
Files changed
Tests added
How to run
Remaining risks
Next recommended task
```

## 6. Public Surface

None. The bot has no public web surface; crawler policy is not applicable.

## 7. Repo and Vault Files

Nothing is generated. `tools/materialize_docs.py` was retired on 2026-10-19 when the docs moved to the vault.

| File | Where | Mode |
|--------|--------|------|
| `AGENTS.md` | repo root (this guide; formerly `docs/build-silverbot.md`) | hand |
| `CLAUDE.md` | repo root; pointer to `AGENTS.md` | hand |
| `README.md` | repo root | hand |
| `docs/index.md` | repo; pointer to the vault project index | hand |
| `.claude/agents/*` | repo; canonical agent cards (snapshot in [sad-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/sad-silverbot.md>) section 3) | hand |
| Model card | [aia-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/aia-silverbot.md>) section 1 (was `MODEL_CARD.md`) | vault |
| Brand and design system | [dsd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/dsd-silverbot.md>) sections 0 to 7 (were `BRAND.md`, `DESIGN.md`) | vault |
| Every other doc | the vault; locations listed in the project index | vault |

## 8. Self-Check

- [x] Read order covers every committed suite doc and RFC.
- [x] Section 5 carries every rule line of the previous `AGENTS.md`.
- [x] Pinned stack values match `pyproject.toml` and `Dockerfile`; none invented.
- [x] Golden-path excerpts are copied from real files with `file:line` and the commit.
- [x] The vault project index and the LOG are named with their vault paths.
- [x] No em dashes.
- [ ] Locked: not yet; every doc is Draft in this pass.
