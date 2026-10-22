# Standalone PROVIDER Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all four agents' internal logic into provider-agents with complete AgentSpecs and behavior-preserving simenv adapters.

**Architecture:** Standalone stateful agents implement the existing validated dictionary contract. Melodie wrappers serialize framework data and apply returned patches, including patches to upstream transports. The committed dependency targets main; development uses a local checkout override.

**Tech Stack:** Python >=3.10, NumPy, Melodie, pytest, JSON Schema, uv, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-22-extract-provider-agents-design.md`

## Global Constraints

- Keep only framework wrappers and adapters in simenv.
- There is no dependency on simenv or Melodie in provider-agents.
- Retain NumPy for the existing `default_rng(seed + id).lognormal(...)` algorithm.
- Every new concrete implementation must include the AgentSpec required by the contract, with schemas for setup input, setup output, step input, and step output.
- The committed dependency declaration must target `main`, not the development branch or an implementation commit.
- Do not commit local path overrides.
- Preserve existing simulation behavior, including seeded results and observable agent state.
- Preserve role-specific error/no-op behavior and route-weight failures.

## Review Focus

1. Downstream source mutations must not be lost when the source's standalone state is used next step (Tasks 5–6).
2. Empty feed-trader input must preserve the previous price, while other empty-input paths clear it as before (Tasks 1 and 4).
3. Tied upstream prices must retain source order during cheapest-first admission (Task 5).
4. Capacity bindings attached after initialization must take effect immediately (Task 6).
5. Python 3.10 imports and schema fallback mode must work without optional runtime dependencies (Tasks 2–5 and 7).

## Repository and file map

Paths prefixed `agents:` are relative to the provider-agents checkout; other paths are relative to simenv.

- `tests/test_agent_equivalence.py`, `tests/fixtures/agent_reference.json`: pre-migration traces and post-migration comparison.
- `agents:src/provider_agents/offis_agents/_common.py`: standalone defaults/state patch helpers and shared schema fragments.
- `agents:src/provider_agents/offis_agents/{farmer,trader,process,transport}_provider_agent.py`: one behavioral implementation and its spec per file.
- `agents:src/provider_agents/offis_agents/__init__.py`: public class and role exports.
- `agents:tests/test_{farmer,trader,process,transport}_provider_agent.py`: direct contract/behavior tests.
- `agents:tests/test_agent_specs.py`: schema and standalone-import coverage.
- `src/provider_simenv/agents/{base,farmer,trader,process,transport}.py`: framework adapters only.
- Both `pyproject.toml` files, simenv `uv.lock`, and both READMEs: dependencies and usage.

## Contract decisions shared by tasks

- Public methods remain `setup(data_in: dict[str, Any]) -> dict[str, Any]` and `step(data_in: dict[str, Any]) -> dict[str, Any]` from the ABC.
- Setup accepts flat behavioral parameters and returns flat initialized behavioral state. `setup({})` exposes zero/default fields before framework parameter assignment; absent role is allowed at this stage. Real initialization happens in `post_setup` with assigned parameters, seed, and id.
- Step accepts an optional `state` mapping of current behavioral fields to synchronize external changes, `effects` mapping of resolved multipliers, `upstream` ordered records, and `peer_count`. Consumer source records additionally carry `recipient_count` for that trader's own active recipients (main #48).
- Source records contain `key`, `quantity_available`, `unit_price`, and `base_yield` where relevant. Transport source records additionally contain `is_transport`, `capacity`, and `effects` where needed for utilisation updates. Keys are strings unique within the ordered input.
- Transport additionally accepts `list_name`, `adjacency` (names to ordered source names), `routes` (name, role, transport-class flag, entity ids), and `route_weights` (entity id to explicitly supplied numeric weight). Missing weights remain missing.
- Step returns flat changed local fields. Transport may additionally return `upstream_updates`, a list of `{key, quantity_available, utilisation?}` records. Adapters strip this special field before applying local state. Inactive steps return `{}`.
- Each implementation defines its own complete `AgentSpec` with id `farmer`, `trader`, `process`, or `transport`, version `1.0`, description, and nested schemas. State properties include all behavioral fields of that class; require setup output fields, allow documented partial step patches, reject unknown message properties, and avoid new numeric bounds that change supported simulations.
- Use only Python 3.10-compatible typing imports. Preserve the existing ABC and fallback semantics; do not redesign the interface or validation engine.

### Task 1: Capture the behavioral reference before extraction

**Files:** Create `tests/test_agent_equivalence.py` and `tests/fixtures/agent_reference.json`.

**Interfaces:** Produce `capture_trace(case: str) -> dict` and a checked-in JSON reference used by Task 6. The trace records per-list/per-agent behavioral attributes, initialization, and each executed step, excluding framework object identities.

- [ ] Verify repository instructions and clean/user-owned changes in both checkouts. Inspect simenv branch ancestry before choosing the PR base; current work began on `49-simulation-api`. Obtain Git author name/email before committing; do not change Git configuration.
- [ ] Write a trace harness using the setup/event-registry pattern in `tests/test_transport_routing.py`. Define cases: baseline 46 days, crisis 46 days, alternate PDL 46 days, nonzero farm-size sigma with seed 42, capacity-limited import at 100 units, and consumer starvation for 22 steps. Record every behavioral field initialized by the old four classes.
- [ ] Generate reference data using the unchanged agent code, then add `test_reference_trace(case)` that compares freshly captured state to the JSON, using exact values for counters/status and tight numerical comparison for floats.
- [ ] Include isolated empty-input and inactive-state reference cases for every role; preserve nonzero prior prices to distinguish clearing from stale-price behavior.
- [ ] Run `.venv/bin/python -m pytest tests/test_agent_equivalence.py tests/test_transport_routing.py -q`; require all cases to pass before touching implementations.
- [ ] Commit only the spec, plan, and reference tests/data once author identity is available. Retain the unmodified implementation commit as the reference provenance in the fixture metadata.

### Task 2: Implement shared standalone state support and farmer

**Files:** Modify `agents:pyproject.toml` and `agents:src/provider_agents/offis_agents/farmer_provider_agent.py`; create `_common.py`, `offis_agents/__init__.py`, `agents:tests/test_farmer_provider_agent.py`, and `agents:tests/test_agent_specs.py`.

**Interfaces:** Produce `FarmerProviderAgent`, its `spec`, and shared state/schema helpers consumed by Tasks 3–5. Export producer/consumer role constants. Shared state application accepts only fields declared by the concrete agent, not arbitrary attributes.

- [ ] Clone provider-agents into a verified local parent directory, read its instructions, create a new extraction branch, and create the companion GitHub issue linking simenv #62. Record its URL for both PRs.
- [ ] Write tests asserting producer setup with yield 100, fixed costs 200, margin 0.1 gives quantity 100 and price 2.2; effects capacity 0.5 and fertilizer 1.2 give quantity 50 and price 5.28. Assert nonzero-sigma size factors equal NumPy's seeded result exactly, unlike the example implementation.
- [ ] Add consumer tests for sharing 100 feed across 2 consumers, zero-input exit on step 21, recovery resetting the counter, inactive `{}`, unknown-role error, and `setup({})` defaults. Add tests that all setup/step dictionaries validate through the public methods.
- [ ] Run these tests against the example and confirm the sampling/contract tests fail for the intended reasons.
- [ ] Replace the example with the simenv farmer behavior using the shared contract above. Add NumPy as runtime dependency and jsonschema to dev dependencies. Implement shared default initialization/state synchronization without model references; no actual random draw occurs for default sigma 0.
- [ ] Run farmer/spec tests with jsonschema installed and monkeypatch the ABC module's `jsonschema` to `None` for fallback tests. Assert required-field failures supported by the fallback and acceptance of valid nested inputs in both modes.
- [ ] Review diff and commit the standalone farmer and shared support, including the companion issue number.

### Task 3: Extract process behavior

**Files:** Create `agents:src/provider_agents/offis_agents/process_provider_agent.py` and `agents:tests/test_process_provider_agent.py`; update public exports/spec tests.

**Interfaces:** Produce `ProcessProviderAgent` and processor/feed-manufacturer role constants, using the shared setup/state/upstream/effects contract.

- [ ] Write parametrized role tests: input quantity 100 at price 10, two peers, conversion 0.8, fixed costs 20, margin 0.1, capacity effect 0.5. Assert input received 50, output 20, and price 14.85.
- [ ] Test empty upstream, zero peers, zero conversion/output, inactive state, and existing unknown-role no-op behavior. Validate complete setup and partial step schemas.
- [ ] Run tests and confirm missing implementation fails; then port defaults, initialization, conversion, and pricing in the original arithmetic order.
- [ ] Run process and farmer/spec tests; require all to pass. Review and commit the process extraction.

### Task 4: Extract trader behavior

**Files:** Create `agents:src/provider_agents/offis_agents/trader_provider_agent.py` and `agents:tests/test_trader_provider_agent.py`; update public exports/spec tests.

**Interfaces:** Produce `TraderProviderAgent` and wholesaler/feed-trader constants; upstream farmer records include base yield.

- [ ] Write wholesaler tests for 100 units at price 10, base yield 80, two peers, storage 40, fixed costs 20, margin 0.1: stock/output 40, utilisation 1, and price 11.55.
- [ ] Write feed-trader tests for weighted upstream pricing, peer division, and empty upstream preserving prior price while stock/output become zero. Test wholesaler empty input clearing price/utilisation, markup initialization, inactive `{}`, and unknown-role no-op.
- [ ] Run tests and confirm missing implementation fails; port both role paths without framework lookups or altered early returns.
- [ ] Run trader, process, farmer, and spec tests. Review and commit the trader extraction.

### Task 5: Extract transport decisions and explicit source updates

**Files:** Create `agents:src/provider_agents/offis_agents/transport_provider_agent.py` and `agents:tests/test_transport_provider_agent.py`; update public exports/spec tests.

**Interfaces:** Produce `TransportProviderAgent`, land/sea role constants, graph-based mode selection, and keyed `upstream_updates` as defined above. All route normalization, sorting, allocation, and utilisation calculations are standalone.

- [ ] Write tests for ordinary movement and export split with peer sharing, energy/capacity effects, initial service price, and zero-input clearing. Verify ignored transit fields do not introduce delay.
- [ ] Write route tests for one route, equal defaults, explicit/unspecified weights, normalized totals over 1, invalid negative/nonfinite values, zero total, and missing declared port errors.
- [ ] Write cheapest-first tests with demand 100 and sources 60 at price 1 and 70 at price 2: source patches admit 60 and 40, output 100, and weighted commodity price 1.4 before freight. Assert transport source utilisation uses its own effective capacity, prices remain unchanged, and tied prices preserve source order. Include a non-transport source and stable key mapping.
- [ ] Test capacity effects above/below 1 against the original capped demand target, exhausted remaining demand, inactive behavior, and invalid roles. Validate nested source/patch schemas with the real validator and valid messages under fallback mode.
- [ ] Run tests to confirm missing implementation fails, then port the existing routing and movement logic using serialized graph metadata. Never mutate input records; return patches.
- [ ] Run the entire provider-agents suite. Review and commit transport implementation and schemas.

### Task 6: Replace simenv agents with framework adapters

**Files:** Modify all five `src/provider_simenv/agents/*.py` implementation modules, `pyproject.toml`, and `uv.lock`; extend `tests/test_agent_equivalence.py` and create `tests/test_agent_adapters.py`.

**Interfaces:** Existing `Farmer`, `Trader`, `Process`, `Transport`, `SupplyChainAgent`, lifecycle methods and role exports remain public. Base adapter owns state publication, synchronization, effects resolution, and source serialization; subclasses supply framework-specific observations only.

- [ ] Write adapter tests asserting default fields exist in wrapper `__dict__`, assigned parameters survive post-setup, setup uses sigma 0 defaults before final seeded initialization, and public contract methods are invoked. Test optional farmer step argument compatibility.
- [ ] Add tests for a capacity binding attached after post-setup and source quantity/utilisation updated by downstream admission, then consumed on the next step without stale state. Test source keys map correctly even when local ids repeat in different lists. Assert unmapped source patches raise an error.
- [ ] Add `provider-agents @ git+https://github.com/PROVIDER-Project/provider-agents.git@main` to runtime dependencies and regenerate the lock against main. Install the local checkout into the development environment with `.venv/bin/python -m pip install --no-deps -e <local-provider-agents-checkout>` if pip is available, otherwise `uv pip install --python .venv/bin/python --no-deps -e <local-provider-agents-checkout>`. Do not persist a local source override or lockfile path reference.
- [ ] Run new adapter tests and confirm they fail against old wrappers. Replace formulas/defaults/role decisions with standalone setup/step calls and dictionary application. Keep framework metadata initialization and existing wholesaler list resolution in the adapter.
- [ ] Serialize route graph/class/entity metadata without selecting economic behavior. Resolve effects and peer/source membership; do not normalize weights or calculate allocation in wrappers. Apply upstream updates before the next list steps.
- [ ] Run `.venv/bin/python -m pytest tests/test_agent_equivalence.py tests/test_agent_adapters.py tests/test_transport_routing.py -q`; require traces to match the original fixtures without regenerating expectations.
- [ ] Review every wrapper for residual economic logic and run the complete simenv test suite. Commit only adapter/dependency/test changes, preserving the main-branch declaration and main-resolved lockfile.

### Task 7: Verify package independence, document, and open both PRs

**Files:** Modify both READMEs and `agents:tests/test_agent_specs.py`; add standalone packaging/import tests there if needed.

**Interfaces:** Produce documented setup/step examples and links to both issues/PRs. Consumers install provider-agents independently; simenv consumes main after the agents PR merges.

- [ ] Add a parametrized test over all four classes asserting `AgentSpec` ids/version/descriptions and all four nonempty schemas. Check schemas with `jsonschema.Draft202012Validator.check_schema`; reject malformed nested messages using the real validator. Exercise valid public calls with the fallback enabled.
- [ ] Add a subprocess import/setup/step test that rejects imports of `provider_simenv` and `Melodie`, proving standalone independence. Run the package tests on Python 3.10 if available; otherwise report that coverage limitation and inspect all new imports for 3.10 compatibility.
- [ ] Document each class's message keys, setup/state ownership, defaults, source update application, schema validation, and a short public-method example. Document local development override commands and the provider-agents-first merge order in simenv.
- [ ] Run provider-agents pytest and Ruff, then simenv `.venv/bin/python -m pytest tests` and configured lint/type checks. Compare any failures to the unchanged base and distinguish existing failures from introduced ones. Re-run only affected checks after fixes.
- [ ] Inspect status/diffs/recent commits in both repositories, confirm no credentials/local overrides, and commit remaining intended documentation/tests using the supplied Git identity. Do not update Git configuration or invent author identity.
- [ ] Push both new branches. Inspect base-branch diffs and all included commits; open linked PRs with `gh`, citing baseline comparisons, test results, companion issue and simenv #62, local-override testing, and merge order. Explain that the committed main dependency needs the provider-agents PR merged before fresh installations exercise the new classes.
- [ ] Return both PR URLs and companion issue URL. If provider-agents has merged during the work, refresh the main-resolved lock and verify a clean install; otherwise record that final main-only installation remains dependent on that merge.
