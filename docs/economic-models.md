# Economic model configuration and evidence

This guide accompanies [simenv #71](https://github.com/PROVIDER-Project/simenv/issues/71)
and [provider-agents #3](https://github.com/PROVIDER-Project/provider-agents/issues/3).
The standalone [model assessment, equations and scientific bibliography](https://github.com/PROVIDER-Project/provider-agents/blob/main/docs/economic-models.md)
documents the research and OFFIS contract 2.0 migration. Merge provider-agents
first; development uses the local editable override described in the root README.

## Selected changes and rationale

The simulation remains a scenario-driven, short-run production network. Cost
exposures can now be decomposed rather than necessarily repricing all farm
operating costs with fertilizer or all freight expense with energy. Processing
can have an explicit throughput ceiling distinct from conversion yield.

ARIO and firm-network models motivate explicit supply bottlenecks and careful
treatment of inventories: Hallegatte (2014),
[doi:10.1111/risa.12090](https://doi.org/10.1111/risa.12090), and Inoue & Todo
(2019), [doi:10.1371/journal.pone.0213648](https://doi.org/10.1371/journal.pone.0213648).
The latter full text explains order/inventory/rationing mechanisms and parameter
limitations. Pichler et al. (2020),
[arXiv:2005.10585](https://arxiv.org/abs/2005.10585), highlights sensitivity to
production-function choices (abstract reviewed). These support the mechanism
choice, not numerical estimates for this soybean scenario. The implemented
model is a single-input fixed-yield bottleneck, not a full ARIO reproduction.

The research assessment also compares CES/Cobb–Douglas production, competitive
storage, origin-differentiated demand and ordering/price adjustment. Those need
commodity recipes, settlement, inventory histories or estimated elasticities
that the current scenario does not supply. The chosen changes improve structural
fidelity; predictive accuracy remains to be established with calibration and
held-out data, following the validation concerns in Windrum et al. (2007),
[JASSS 10(2),8](https://www.jasss.org/10/2/8.html) (full text reviewed).

## Sidecar shape

Place optional `economics` beside `archetypes`, `entities`, `edges` and
`dependencies` in the matching `*.roster.yaml`. Keys are resolved roster names:
PDL/sidecar entity ids, or `sea_transport_<source>__<destination>` for a derived
crossing. Names are validated against this scenario's roster, never a fixed
country/port list. Excluded input commodities remain valid binding targets.

Example for entities in the shipped PDL (all values below are **illustrative**,
not fitted coefficients):

```yaml
economics:
  brazil_farms:
    parameters:
      base_yield: 100.0
      fixed_costs: 36000.0
      input_cost_shares: {nutrients: 0.25}
    bindings:
      nutrients: [fertilizer_supply, price]
  eu_oil_mills:
    parameters:
      throughput_capacity: 200.0
      conversion_ratio: 0.8
      input_cost_shares: {energy: 0.2}
    bindings:
      energy: [gas_supply, price]
  sea_transport_santos_port__rotterdam_port:
    parameters:
      capacity: 1000.0
      margin: 0.1
      input_cost_shares: {energy: 0.4}
    bindings:
      energy: [gas_supply, price]
```

Each entry accepts only `parameters` and `bindings`. Each positive configured
cost share must resolve to a **price** binding. `capacity` is a reserved physical
slot and cannot be a cost-share key or an explicit sidecar binding; own-entity
`supply` effects still bind automatically. Other binding fields may be `supply`
or `price`. A typo, unknown target, unsupported role parameter, invalid type,
nonfinite number, negative value or total cost share above one fails loading.
Zero-valued cost shares need no binding. Empty `input_cost_shares: {}` explicitly
disables operating-cost exposure. Missing `economics` is supported.

### Allowed parameters and units

| Parameter | Roles | Unit/domain |
| --- | --- | --- |
| `fixed_costs` | all | Baseline operating expense, currency/step; finite nonnegative |
| `input_cost_shares` | all | Slot-to-cost-fraction mapping; finite nonnegative, total<=1 |
| `margin` | producer, traders, processing, transport | Nonnegative markup fraction; maps to `margin_transport` for transport |
| `base_yield` | producer | Baseline output tonnes/step; finite nonnegative |
| `capacity` | land/sea transport | Offered input throughput tonnes/step; finite nonnegative |
| `throughput_capacity` | processor/feed manufacturer | Input tonnes/step **per agent**; null (default) or finite nonnegative |
| `conversion_ratio` | processor/feed manufacturer | Output/input tonnes; finite strictly positive |
| `storage_capacity` | wholesaler | Current same-tick handling cap in tonnes, not persistent inventory |
| `transit_steps` | land/sea transport | Nonnegative integer; descriptive only, no delay is implemented |

Consumer costs/shares are configurable state but do not create consumer demand
or a financial ledger. Current consumer behavior is feed sharing and operational
starvation. Do not interpret its exit threshold as a calibrated bankruptcy model.

### Resolution and defaults

1. Existing archetype and scenario defaults are resolved normally.
2. Economic `parameters` override the corresponding literal or scenario value
   before standalone setup. `bindings` merge with producer dependency bindings;
   explicit aliases win.
3. Normal seeded farmer-size scaling occurs once during setup, after parameters
   are resolved. A fixed-cost/base-yield override is a pre-size baseline.
4. The adapter forwards resolved state/effects; it does not overwrite configured
   transport margins with the scenario default on subsequent steps.

Without explicit shares, producers retain fertilizer share=1, transport energy
share=1, traders/processors empty. These preserve the old **illustrative**
assumptions; they are not empirical estimates. The shipped CLI and configurator
sidecars explicitly
declares transport energy relationships and the oil mill's energy binding.
The oil-mill binding only changes costs after a nonzero energy share is supplied.
Python no longer embeds a relationship to a particular gas-supply entity.
Configurations without energy bindings run with neutral effects; add bindings
explicitly when upgrading an older custom roster that relied on that implicit link.

Keep data provenance (source, observation date, unit, uncertainty and aggregation
level) in YAML comments or accompanying scenario documentation. No provenance
metadata is accepted inside the strict economic parameter mapping. Existing
PDL/sidecar hashes identify the actual run configuration.

## Equations and observability

For baseline operating cost F, shares s and resolved price multipliers m:

`F_effective = F * (1 - sum(s) + sum(s[k] * m[k]))`.

The residual share is unexposed. Missing prices are neutral. Upstream commodity
prices are not repriced a second time. With F=100, exposed share=.25 and m=2,
operating cost is 125.

For processing offer A, yield y, capacity effect c and explicit throughput K:

`processed = min(A, K*c); output = y*processed; unused = A-processed`.

If K is null, the fallback is `processed = min(A, A*c)`: proportional availability,
not an absolute capacity estimate. K=0 means closed. Positive output is quoted
at `(weighted_input_price/y + F_effective/output) * (1+margin)`.
For A=100, K=50, c=1, y=.8, input price=10, F=20 and margin=.1, output=40,
unused=50, quote=14.3. Halving capacity processes 25 and outputs 20; a 20-tonne
offer is still processed in full under that same 25-tonne effective ceiling.

CSV and PostgreSQL record three appended metrics for both processing roles:
`input_received` (equal-share **offer**), `input_processed` (transformed input),
`unused_input` (unprocessed offer). These are input units/period, not settled
purchases or carried inventories. Older database periods have null diagnostics.
The static globe bundle retains its existing public fields and valid JSON;
recorded-run playback exposes the raw additional metrics. See
[database schema](postgres-schema.md).

## Explicit limits and future PDL fields

- No persistent inventory, purchase/sale settlement, energy quantity bottleneck,
  endogenous consumer demand or market clearing. Quotes are not transaction prices.
- No shipment queue: `transit_steps` does not delay arrivals. The DAG still
  propagates material through several stages in one tick.
- A conversion ratio below one leaves coproduct/waste outside the modeled
  output. Soy-oil revenue and nutritional feed conversion are not modeled.
- Current graph sharing restrictions prevent some double counting but are not a
  general material/cash conservation engine. Unused offers are not carried forward.
- Move the economic section into PDL once it defines typed per-entity production
  capacities, yields, expense components, semantic price bindings and units.
  Future inventory/transport models additionally need opening stock, losses,
  input recipes, lead times, order links and one-time allocation/settlement.
- Demand/substitution needs requirements, commodity/nutrient groups, quality
  constraints, budgets and empirical elasticities. Do not hardcode new
  relationships or infer new suppliers outside scenario declarations.

## Verification and empirical follow-up

Run the Python regressions and tox as documented in AGENTS.md, with a local
editable agents checkout for unmerged changes. `tests/test_economic_config.py`
checks renamed entities, valid/invalid configuration and precedence;
`tests/test_economic_integration.py` checks real graph execution, standalone
parity, cost reconciliation, recordings and historical exports. Set
`SIMENV_TEST_POSTGRES_URL` to exercise the isolated database/view upgrade test.

For empirical validation, collect plant utilization/yield/cost-share and supply
data; calibrate on separate baseline/disruption windows; hold out an event;
compare price/volume errors against the old model and simple reference forecasts;
and report parameter/seed/timing sensitivity. The provider-agents assessment
details that protocol and the source-access levels for all ten cited papers.
