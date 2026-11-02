# Economic Model Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve economic cost exposure and processing constraints across simenv #71 and provider-agents #3, backed by scientific research and tests.

**Architecture:** Reusable equations and validated dictionary contracts live in provider-agents. A focused simenv resolver translates PDL/sidecar parameters and bindings to those contracts; adapters remain thin. Existing CSV/PostgreSQL metric machinery records the new processing diagnostics.

**Tech Stack:** Python 3.10+, NumPy, optional jsonschema, Melodie, PyYAML, pytest, Ruff, tox/ty, PostgreSQL integration where available.

**Spec:** `../specs/2026-11-02-economic-models-design.md`

## Global Constraints

- Python 3.10+; provider-agents remains independent of simenv and Melodie.
- Keep simenv's runtime dependency on provider-agents main; use only a local editable override for cross-repository verification.
- All scenario nodes/relationships come from PDL/sidecar; no new hardcoded node relationships in Python.
- Preserve unrelated staged AGENTS.md in the original checkout.
- User approved focused scope and requested independent GPT6-Astra high plan and implementation review loops.
- Commit/push/open PRs only with explicit user authorization. After clean final reviews, the user authorized publishing both branches and linked PRs.

## Review Focus

1. Externally synchronized invalid economic parameters must fail even without optional jsonschema (Task 1/2).
2. Zero capacity, capacity gains and underutilized explicit capacity must not conflate throughput and yield or create input (Task 2).
3. Sidecar keys, dependency aliases, excluded-but-valid input entities and derived sea-route names must resolve deterministically and reject typos (Task 3).
4. Repeated setup/step must not share mutable exposure dictionaries between agents or modify caller data (Task 1).
5. New PostgreSQL view columns must append safely and historical recordings remain readable (Task 4).

## Workspaces and verification

- Simenv: `/data/home/repositories/simenv/.worktrees/issue71`, branch `71-economic-models`, base `9dee6b0`.
- Agents: `/tmp/opencode/provider-agents`, branch `3-economic-models`, base `b6118ad`.
- Shared verification environment: `/tmp/opencode/issue71-venv`; install simenv development dependencies then local agents development extra.
- Before implementation, run both baseline suites and record failures/skips.

### Task 1: Standalone cost-exposure policy

**Files (provider-agents):** create `src/provider_agents/offis_agents/economics.py`, `tests/test_economics.py`; modify `_common.py` and all four `*_provider_agent.py`; update contract tests.

**Interfaces:** `validate_cost_shares(shares: dict[str, float]) -> None`; `operating_cost(base: float, shares: dict[str, float], effects: dict[str, float]) -> float`. The helper validates finite nonnegative exposures/multipliers and sum<=1. Each actor publishes `input_cost_shares` through setup/defaults/state schema.

- [ ] Add failing tests: F=100, fertilizer share .25, multiplier 2 gives 125; two exposed components and residual reconcile; absent multipliers are neutral; empty shares ignore unrelated effects. Parameterize invalid bool/string/negative/NaN/infinite shares, totals above one and malformed mappings with and without jsonschema.
- [ ] Run `python -m pytest tests/test_economics.py` and confirm failure from missing behavior.
- [ ] Implement shared policy; use it only on the actor's operating cost, preserving upstream prices. Deep-copy mutable defaults and synchronized values. Set OFFIS contract versions to 2.0 without changing the abstract interface default.
- [ ] Add actor-level price tests for producer, trader, processor and transport; mutation-isolation and synchronized-invalid-state tests, including negative/nonfinite/boolean baseline cost. Preserve legacy default price expectations.
- [ ] Run `python -m pytest tests` and `ruff check .` in provider-agents; resolve only issue-related regressions.

### Task 2: Processing throughput and input diagnostics

**Files (provider-agents):** modify `process_provider_agent.py`, `tests/test_process_provider_agent.py`, `tests/test_agent_specs.py`.

**Interfaces:** process defaults/setup/state add `throughput_capacity: float | None`, `input_processed: float`, `unused_input: float`; process actions contain existing fields plus the latter two diagnostics. `input_received` retains equal-share offer semantics. New fields are zeroed on empty-input paths.

- [ ] Add failing analytical tests for 100 input at 10, yield .8, explicit capacity 50, overhead 20, margin .1: processed=50, unused=50, output=40, quote=14.3, cost before markup=520. Repeat with capacity effect .5 (processed=25), low supply=20 (not 10), cap=0 and cap=null.
- [ ] Test effect>1 cannot create input; peers divide offers only, not the per-agent capacity; zero/negative/nonfinite yield, cap/effect/quantities/prices and negative/fractional/boolean peer counts reject with and without jsonschema. Inactive/unknown roles remain no-op. Test one-shot setup then externally synchronized invalid state, unchanged caller sources and a two-source unequal-price weighted-cost example.
- [ ] Run focused tests to establish failure, implement the spec equations and domain validation, then rerun focused and complete standalone suites.

### Task 3: PDL/sidecar economic configuration

**Files (simenv):** create `src/provider_simenv/economic_config.py`, `tests/test_economic_config.py`; modify `topology.py`, `agents/transport.py`, `model.py` for assignment precedence, and `scenarios/s1-soja.roster.yaml`.

**Interfaces:** `resolve_economics(roster, raw_economics, entity_ids) -> list[RosterEntry]` returns fresh immutable archetypes with merged copied attrs/bindings; role-appropriate allowlists come from explicit constants, not unrestricted agent state. Loader's `RosterSidecar` adds economics with an empty default.

- [ ] Add failing tests for economic overrides before setup (literal economic attrs beat scenario_attrs), explicit slot aliases, unknown target/parameter/role, reserved capacity binding/share, missing referenced entity, unsupported impact fields, positive exposure bound to supply rather than price, malformed sections, nonfinite YAML values and missing exposure binding. Treat the sidecar as untrusted input, including wrong root/entry types.
- [ ] Add renamed synthetic-PDL tests with non-soy names and excluded input commodities, plus derived sea route targets; one entity's override cannot alter another's defaults. PDL without economics still builds and runs.
- [ ] Implement small resolver and call it after all roster entries are known. Remove Python's `gas_supply` relationship; declare shipped port/sea energy bindings in sidecar and the existing oil-mill energy binding explicitly. Default shares remain compatibility assumptions; avoid synthetic empirical estimates.
- [ ] Map sidecar transport `margin` to `margin_transport`; move scenario fallback into archetype scenario_attrs and remove unconditional transport-adapter overwrites. Verify configured margins survive setup and multiple steps, including derived sea routes; unconfigured routes keep scenario defaults.
- [ ] Run `python -m pytest tests/test_economic_config.py tests/test_agent_adapters.py tests/test_transport_routing.py tests/test_feed_allocation.py tests/test_topology_snapshot.py`.

### Task 4: Recording and cross-repository integration

**Files (simenv):** modify `data_collector.py`, `db_schema.py`, `export_bundle.py`; create `tests/test_economic_integration.py`; extend existing recording tests only as needed.

**Interfaces:** append `input_received`, `input_processed`, `unused_input` to processor/feed-manufacturer recorded properties; catalogue units are input units per period. Preserve pre-existing metric names and view-column order.

- [ ] Add failing real-model tests using a custom PDL/sidecar and shock tracker: capacity shocks bind absolute throughput, selective input price shocks propagate once, and quotes reconcile with processed-input costs. Exercise baseline and shock steps, run_stepwise, and standalone/adapter parity.
- [ ] Add catalogue/CSV recording assertions and a PostgreSQL integration assertion when the configured service is available. Verify existing views can be replaced with appended columns and historical missing metrics read null.
- [ ] Define exporter properties independently from recorded properties, preserving current public bundle fields. Test historical CSVs without diagnostics against historical database null diagnostic rows, and new recordings; assert public-value parity and `json.dumps(bundle, allow_nan=False)` succeeds.
- [ ] Implement recording additions; run relevant recording, API and export suites. Inspect skips and report service blockers.

### Task 5: Research, migration and final review

**Files:** provider-agents `docs/economic-models.md`, `README.md`; simenv `docs/economic-models.md`, `README.md`, `web/README.md`, `docs/postgres-schema.md`; this plan and design/review log.

- [ ] Write an extensive but focused model comparison with verified scientific citations, access level, applicability, equations and adoption/defer reasons. Add a storage/demand source only after verification. Include numerical cost/throughput examples, compatibility assumptions, limitations and a concrete calibration/holdout evaluation protocol.
- [ ] Document sidecar schema/examples, units, validation and precedence, input-offer semantics, no carryover, no endogenous demand/market-clearing and unchanged transport-delay limitation; document OFFIS 2.0 migration and agents-first merge order.
- [ ] Review README.md, web/README.md and relevant docs against actual behavior; correct stale statements that sidecar actors/edges are unwired. No frontend UI work is needed.
- [ ] Run agents `python -m pytest tests` / `ruff check .`; simenv `python -m pytest tests` / `python -m tox`. Use a temporary tox dependency override for local agents without changing committed main dependency. Record exact commands, counts, skips and blockers.
- [ ] Have two independent GPT6-Astra high reviewers inspect full diffs and tests. Address findings, rerun affected checks and repeat independent reviews until both report no actionable findings.
- [ ] Review both full diffs against origin/main and git status; deliver branch/worktree paths, plan/research locations, verification and review results. Ask for commit/push/PR authorization if it has not been granted.

## Plan review log

Round 1: two independent OpenCode plan agents, `openai/gpt-6-astra`, variant
`high`, requested revisions. Accepted all four unique findings: transport
margin precedence, price-only cost bindings, missing processing-domain tests,
and export/recording property coupling. Incorporated each into spec and tasks.
Round 2: two fresh independent GPT6-Astra high reviewers both returned
"No actionable findings. APPROVE". User then approved the written plan and
inline implementation with repeated independent implementation reviews.

## Execution ledger

Pre-flight: cost-share state/schema is consumed by all actors and the simenv
resolver; process actions are consumed by the adapter and recorder; recording
properties are intentionally separate from export properties. Interfaces agree.

Tasks 1–2: tests first demonstrated missing cost-share/throughput behavior and
invalid-state acceptance. Standalone suite now 114 passing; Ruff passes.
Fallback validation exposed a null/minimum schema incompatibility; represented
nullable capacity with anyOf while retaining semantic validation.

Task 3: 26 tests first demonstrated ignored sidecar configuration and invalid
input acceptance. Focused tests now pass; updated intentional topology snapshot
changes (transport scenario margin resolution and explicit oil-mill binding).

Ruling: remove overridden scenario_attrs in the resolver rather than changing
global model setup order — enforces the same scoped precedence without changing
all archetype initialization; a mistaken mapping would affect configured actors.

Task 4: recorded diagnostics and a real PostgreSQL view upgrade are exercised.
Export regressions demonstrated historical NaN and unwanted public fields before
decoupling the projection. Subsequent validation and final review pending.

Environment: new virtualenv dependency downloads timed out; a separate Python
3.11 environment uses existing development dependencies via a .pth overlay and
local editable installs for both repos. Original environment/checkouts untouched.
`npm ci` installed esbuild in the worktree and resolved its baseline test error.
An isolated Podman PostgreSQL 16 instance uses 127.0.0.1:55471 for integration.

Task 5: research/integration/migration docs written and README/web/schema docs
reviewed. Research compares ten verified bibliographic sources; access levels
and absence of empirical calibration are explicit.

Implementation review round 1: two independent GPT6-Astra high agents found
four unique important issues. Each was reproduced RED then fixed GREEN:
default-share price binding semantics, dangling inferred exposure targets,
zero-flow price-effect validation, and the configurator's separate roster
template migration. Added real CSV/PostgreSQL old/new public-value parity.
Agents: 122 passed, Ruff passed. Simenv PostgreSQL-enabled suite: 226 passed,
4 opt-in run-parity checks skipped, one known-broken baseline playback test
explicitly deselected after reproducing its scenario-0 failure on base 9dee6b0.

Configured tox executed with a temporary `UV_OVERRIDE` pointing to local agents:
`PATH=/tmp/opencode/issue71-venv/bin:/data/home/repositories/simenv/.venv/bin:$PATH UV_OVERRIDE=/tmp/opencode/issue71-overrides.txt python -m tox -x 'testenv.pass_env+=UV_*'`.
Test environment: 214 passed, 17 skipped (database opt-ins absent in tox).
Lint/typecheck fail on baseline debt: Ruff 13 diagnostics versus base 14;
ty with the same full development environment has 51 diagnostics on both
base and issue worktrees. Tox's narrower typecheck environment lacks pytest
and reports additional unresolved test imports (73 total). No new-code ty
diagnostics remain in the full development environment.

Frontend: `npm ci`, `npm run typecheck`, `npm run lint`, `npm run build` pass.
`npm run test:simulation` attempted against its default URL, but reached an
existing unrelated server and failed disabled-button assertion; it is not a
passing controlled acceptance run. The current browser script also retains
the pre-existing 730-step assumption, inconsistent with issue64's 365 steps.
No UI layout changed; only the roster template's economic binding data changed.

Ruling: honor the user's requested repeated independent review loop rather
than the execution skill's default one-review limit. Deferred model classes,
state rollback after validation errors, and legacy allocation rules retain
their approved boundaries; documentation states their limitations. Baseline
quality/test failures are reported rather than hidden or attributed to this work.

Implementation review round 2: two fresh independent GPT6-Astra high reviewers
returned "No actionable findings. APPROVE". One independently ran the complete
122-test standalone suite; the other ran 95 focused standalone tests. They also
ran 37 and 3 focused simenv checks respectively and reviewed all changed/new
files and the PostgreSQL parity regression.

Final follow-up: a real CLI run, `20261102T102756Z-2d518a4f`, completed baseline
and shocked scenarios, 365 days each, with PostgreSQL and CSV recording. Then
all four opt-in `tests/test_postgres_csv_parity.py` checks passed against that
run (no skips), including every raw value and both scenario bundles.
`ty check` on the new economic module and both new test modules passes.

## Execution status

The task checklists above preserve the reviewed work instructions. All five
deliverables are implemented and verified as described in this ledger. Both
plan and implementation review loops ended with two independent approvals.
No actionable review findings or deferred minor findings remain. The approved
model limitations and pre-existing test/quality debt remain explicitly recorded.

Publishing was explicitly authorized after the final review. Both PRs will
record their own closing issue link and the agents-first merge dependency.
