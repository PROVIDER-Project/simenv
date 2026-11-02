# Economic model improvements: simenv #71 / provider-agents #3

## Intent and approved scope

Improve the structural accuracy of the soybean disruption simulation using
scientific literature, clean reusable policies, and scenario-owned parameters.
The user approved a focused design: cost exposures, capacity-constrained
processing, validated PDL/sidecar configuration, and a research comparison.
Predictive accuracy requires calibration and empirical holdout data; the
deliverable must not equate passing accounting tests with empirical validation.

## Alternatives and decision

1. **Focused production/accounting improvements (selected).** Retain standalone
   OFFIS agents and thin Melodie adapters. Correct identifiable assumptions and
   expose parameters, with analytical and cross-repository regression tests.
2. **Transactional production-network engine.** Orders, supplier settlement,
   persistent inventories and shipment queues would support ARIO-style dynamics,
   but require coordinated new contracts and scheduling throughout the system.
3. **Equilibrium/CES replacement.** Substitution and endogenous price formation
   require commodity groups, expenditure shares and elasticities absent from
   the current scenarios. Adding guessed elasticities would not establish
   improved accuracy.

## Boundaries and data flow

- `provider-agents` owns economic equations, plain-dictionary state and schemas.
  It remains independent of PDL, simenv and Melodie.
- `simenv` owns PDL effects, sidecar validation, parameter resolution, graph
  ordering, observations and recording. No new node identifiers or relationships
  appear in Python. Existing transport energy relationships move to the sidecar.
- The existing graph allocation restrictions remain: this change does not
  introduce a general transaction ledger or claim full-chain conservation.

## Cost exposure policy

All four OFFIS implementations accept `input_cost_shares`, a mapping from
semantic effect slots to nonnegative finite baseline operating-cost shares.
Shares sum to at most one. For baseline operating cost F and resolved input
price multipliers m[k], use:

`F_effective = F * (1 + sum(s[k] * (m[k] - 1)))`.

The residual share is unexposed. Only operating cost is scaled; upstream
commodity purchase prices already carry their own shocks and are not scaled
again. Missing effect slots are neutral (one). Relevant multipliers must be
finite and nonnegative. Boolean values are not numbers for these parameters.

Defaults preserve the existing exposure assumptions: farmer fertilizer=1,
transport energy=1, trader/process empty. These are compatibility assumptions,
not estimates. Explicit `{}` disables exposure. New configurations should supply
measured shares. The shipped sidecar labels compatibility assumptions and
declares transport energy bindings; no invented calibrated percentages.

Use one standalone helper module for equations and semantic validation. Copy
mutable mappings during setup and state synchronization to avoid shared state.
Validation must work with and without optional jsonschema.
Baseline cost must also be finite, nonnegative and nonboolean, including when
synchronized externally. Cost-share slot `capacity` is reserved and rejected.

## Processing policy

`throughput_capacity` is optional (`null` means unconstrained absolute input
throughput; zero means closed), in input tonnes/step. `conversion_ratio` is
finite and strictly positive. A capacity effect is finite and nonnegative.

For upstream total Q, active peers n, yield y and effect c:

- `input_received = Q / n` (the existing equal-share input offer).
- With explicit capacity K: `input_processed = min(input_received, K * c)`.
- With null K: `input_processed = min(input_received, input_received * c)`.
  This preserves the legacy proportional-availability fallback for losses;
  supply gains never manufacture input. It is not an absolute capacity model.
- `unused_input = input_received - input_processed`.
- `quantity_available = y * input_processed`.
- For positive output: `unit_price = (weighted_input_price * input_processed +
  F_effective) / quantity_available * (1 + margin)`; zero output has zero price.

Input records are offers, not settled purchases. `unused_input` is unprocessed
offered material this tick, not a persistent inventory or loss. Upstream offers
are not mutated. The non-output fraction implied by y is outside this
single-output model (coproduct/waste); no oil-market accounting is claimed.
Empty sources or zero peers clear all processing flow fields. Inactive/unknown
roles retain their existing no-op behavior. Invalid new economic parameters
fail explicitly, including externally synchronized state. Zero yield, previously
accepted with no output, becomes a validation error rather than division risk.
Processing source quantities/prices must be finite nonnegative nonboolean
numbers; peer count must be a nonnegative nonboolean integer, even without
jsonschema. Test unequal-price sources as well as single-source examples.

## Contract and configuration

Version the changed OFFIS contracts as `2.0` and document migration, particularly
the new required setup-output fields and process action fields. The abstract
interface default remains unchanged. Preserve no-configuration normal-flow
arithmetic where practical; update assertions only for intentional changes.

Extend the sidecar with optional `economics`, keyed by resolved roster name
(entity id or the existing derived sea-transport name). Each entry accepts only:

- `parameters`: a role-appropriate subset of `fixed_costs`, `margin`,
  `input_cost_shares`, `base_yield`, `capacity`, `throughput_capacity`,
  `conversion_ratio`, `storage_capacity`, `transit_steps`.
- `bindings`: semantic slot to `[PDL-or-sidecar-entity-id, impact-field]`.

Parameters override archetype/scenario defaults before post-setup. Bindings
merge with inferred producer bindings; explicit bindings win. The existing
automatic own-entity supply/capacity binding remains authoritative; explicit
capacity bindings are rejected to avoid silently ignored input.
For transport, sidecar `margin` maps to standalone `margin_transport`. Move its
scenario fallback into archetype scenario_attrs and remove the adapter's
unconditional scenario overwrites in setup and step. Test persistence across
multiple ticks and a derived route.

Reject malformed sections, unknown roster targets/fields, inappropriate
role parameters, nonfinite/out-of-range values, invalid mapping shapes and
bindings to nonexistent entities. Share keys must have a resolved binding
(except zero-valued shares); report an unbound configured exposure rather than
silently ignoring a typo. Absent `economics` remains supported. Do not allow
arbitrary `setattr` from sidecar keys. Keep this focused validation/resolution in
a new module, rather than substantially enlarging topology.py.
Positive cost exposures must bind specifically to `price`, never `supply`;
other binding fields must be among the runtime-supported `price`/`supply`.

The sidecar contains the missing configuration until PDL gains typed economic
parameters and explicit binding slots. Document units, defaults, precedence,
derived-route naming, provenance and migration requirements. Scenario hashes
already include sidecars; preserve that provenance mechanism.

## Observability and compatibility

Record `input_received`, `input_processed`, `unused_input` for processor and feed
manufacturer roles in CSV and PostgreSQL. Add catalogue entries and append view
columns, preserving existing column names/units and historical records. Existing
historical rows lack the new metrics and return null; exports keep their current
public bundle contract. Frontend configurator output remains valid with no
economics section; document that custom economic settings are authored in YAML.
Decouple exporter property selection from recorded properties so historical
PostgreSQL null diagnostics do not enter bundles as NaN, and new recordings do
not add public bundle fields. Test old/new CSV/PostgreSQL parity and strict
JSON serialization (`allow_nan=False`).

## Research and validation

Create a standalone models/research document in provider-agents and an integration
guide in simenv. Include a source-verification table, existing-model audit,
equations, numerical examples, and comparison of fixed-coefficient bottlenecks,
Cobb-Douglas/CES, adaptive inventories, competitive storage, demand/substitution,
price adjustment and ABM validation. Distinguish scientific support for a
mechanism from evidence for scenario parameter values.

Verified starting sources: Hallegatte (2008), DOI
10.1111/j.1539-6924.2008.01046.x; Hallegatte (2014), DOI 10.1111/risa.12090;
Inoue & Todo (2019), DOI 10.1371/journal.pone.0213648 (full text inspected);
Pichler et al. (2020), arXiv:2005.10585; Arrow et al. (1961), DOI
10.2307/1927286; Lee et al. (1997), DOI 10.1287/mnsc.43.4.546; Windrum et al.
(2007), JASSS 10(2),8 (full text inspected). Extend verification for storage and
demand references before making claims about them.

Tests must establish selective exposure, cost reconciliation, throughput/yield
separation, no input creation, deterministic state synchronization, source
immutability, arbitrary renamed topology, invalid-input rejection, fallback
validation, no-economics compatibility and CSV/PostgreSQL catalogue consistency.
Run both complete regression suites, simenv tox, and relevant database/API
integration checks when available; explicitly record skips/environment blockers.
Independent GPT6-Astra high reviewers repeat plan and implementation reviews
until neither reviewer has unresolved actionable findings.
