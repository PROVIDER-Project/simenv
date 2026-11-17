# Data used by simenv and its frontend beyond the PDL

**Audit date:** 2026-10-28
**Repository:** PROVIDER-Project/simenv
**Inspected checkout:** `62-extract-provider-agents`, commit `d3146f33b582220362539a43c
e71b7fbe8532ab8` (clean working tree at inspection).
**Open issues:** all 23 open issues retrieved from GitHub, including the comment on #25
.

**Historical audit:** the findings below describe the inspected 2026-10-28
checkout, not the current implementation. In particular, Issue #84 adds individual
land/sea transport recordings and effective-capacity-weighted static utilization;
the old statements that port/sea agents have no series are historical. Current
contracts and local-source UI rules are in [PostgreSQL schema](postgres-schema.md),
[Database playback](playback.md) and the
[Santos capacity investigation](economic-models.md#santos-capacity-investigation-issue-84).

## Executive summary

The PDL is currently **not a self-contained simulation specification**. It describes en
tities, qualitative metadata, supply-chain stages/dependencies, substitutions, disrupti
on magnitudes/durations, and cascade schedules. Running and displaying it additionally
requires:

1. A **roster sidecar** defining executable roles, exclusions, four trading actors, ele
ven connecting edges, and two additional input dependencies.
2. **Model calibration outside the PDL:** costs, margins, baseline production, capaciti
es, route shares, size distributions, random seed, run length, and behavioral assumptio
ns.
3. **Geography outside the PDL:** a country-to-continent classifier, twelve frontend co
ordinate/label fallbacks, and coordinates for the four sidecar actors.
4. **Generated state and operational metadata:** computed prices/volumes, activity, met
rics, run identity/provenance/progress, and the JSON playback contract.
5. **Frontend interpretation rules:** normalized disruption intensity, animation/presen
tation settings, and scenario-editor defaults/limits.

The first three groups are the most consequential missing scenario inputs. Generated re
sults and UI state are additional information, but are not automatically deficiencies i
n an input language.

The strongest future-data signals are issues **#41/#25 (geography), #8 (entity calibrat
ion), #45 (consumer semantics), #6 (substitution execution), #60/#53/#59 (run identity,
 provenance, result exchange), and #64 (one scenario per request)**. Several older open
 issues describe work already present in this checkout; their open status alone is not
evidence that the old behavior remains.

## Scope and comparison method

“Not specified in the PDL” here means absent from the shipped [`s1-soja.pdl.yaml`][pdl]
, or an interpretation/calibration supplied by executable code rather than by that docu
ment. This audit does **not** establish what a separate, authoritative PDL schema permi
ts: no formal PDL schema was identified in the inspected application sources. In partic
ular, the exporter already accepts entity coordinates in PDL documents even though the
shipped PDL supplies none.

I compared the parsed PDL against the sidecar, traced roster construction and parameter
 assignment into agent setup/step inputs, followed recorded properties through the expo
rter to the frontend, and reviewed every open GitHub issue against current code. A read
-only Python probe executed the actual `build_roster`, `build_flow_adjacency`, and `der
ive_sea_edges` functions. It confirmed:

- **20 PDL entities**, of which 12 become node agents and 8 are explicitly excluded as
node agents.
- **4 additional sidecar entities**, **11 sidecar stage edges absent from the PDL stage
s**, and **2 sidecar dependencies absent from the PDL dependencies**.
- **4 derived sea-transport agents**: Santos→Rotterdam, Paranaguá→Hamburg, Argentina fa
rms→Rotterdam, and US Gulf ports→Rotterdam.
- **20 runtime roster entries** in total: 16 node agents plus 4 sea agents; `model.setu
p()` creates one agent per entry.
- **No coordinates on any of the 20 shipped PDL entities**. Twelve modeled PDL entities
 use the frontend gazetteer; four added actors carry sidecar coordinates.

**Dependency boundary:** agent decision logic has moved into `provider-agents`. The ins
talled dependency resolves to `/tmp/opencode/provider-agents-62`, commit `e780690d643d6
4de5e5ff6067a1086a945a6b5f6` (clean at inspection). I inspected those installed impleme
ntations to verify which parameters are actually consumed. `pyproject.toml:7–11,40–42`
declares the moving `main` branch, so another installation can resolve differently. Ref
erences prefixed `provider-agents/` below refer to this inspected dependency, not files
 within simenv.

## 1. Additional actors, graph links, and executable roles

### 1.1 Trading actors and their connecting edges — additional domain data

**What is absent:** `brazil_wholesaler`, `argentina_wholesaler`, `us_wholesaler`, and `
eu_feed_trader` do not appear in the PDL entity list. The sidecar introduces their name
s, roles, reasons for addition, coordinates, and illustrative-placement flags. Its elev
en edges insert grain originators between farms and logistics and a feed distributor be
tween feed mills and livestock farms.

**How the difference was found:** compared entity-ID sets and exact stage pairs from th
e parsed PDL with `sidecar.entities` and `sidecar.edges`; then traced the merged entiti
es in `build_roster()` and stage replacement in `build_flow_adjacency()`. The runtime a
djacency confirms the added actors are active graph participants, including Argentina w
holesaler→derived sea lane→Rotterdam.

**What it is used for:** wholesalers aggregate farm supply, limit stock to storage capa
city, and compute selling prices. The feed trader distributes feed and adds distributio
n costs/margin. Both roles supply environment-level price indicators and recorded front
end series. These are behaviorally significant additions, not merely visual map markers
.

**Evidence:** [sidecar lines 30–73][roster]; `topology.py:375–428,482–582`; `environmen
t.py:146–178`; `provider-agents/offis_agents/trader_provider_agent.py:53–96`.

### 1.2 Executable archetypes, exclusions, and agent cardinality — model interpretation

**What is absent:** PDL `type`/`sector` values do not fully define executable roles. Th
e sidecar maps the twelve modeled PDL entities to `producer`, `land_transport`, `proces
sor`, `feed_manufacturer`, or `consumer`, and explicitly excludes eight others as node
agents. For example, both oil mills and feed mills are PDL `manufacturer/processing`, b
ut their execution roles differ. The registry also supplies wholesaler/feed-trader role
s. One agent per roster entry is a code rule, not a population count stated by the PDL.

**How found:** compared PDL entity fields with `sidecar.archetypes`/`exclude`, followed
 `resolve_archetype()` precedence and the `(type,sector)` fallback, and checked `setup_
agents(1)` rather than relying on historical comments about pooled/multiple agents.

**Use:** selects the decision implementation, initialization recipe, shock bindings, ou
tput metrics, and whether an entity exists as a runtime actor. Exclusion is specificall
y exclusion from node-agent modeling: `gas_supply` remains a shock-binding target and `
us_gulf_ports` still anchors a derived sea crossing.

**Evidence:** `s1-soja.roster.yaml:4–28`; [topology lines 154–202][topology]; `model.py
:73–94`; `data_collector.py:19–29`.

### 1.3 Extra input dependencies and hardcoded effect bindings

**What is absent:** the sidecar adds Argentina farms→fertilizer supply and US farms→fer
tilizer supply, both `input/medium`. The PDL explicitly declares Brazil’s fertilizer de
pendency, and separately lists fertilizer overlap in substitution metadata; that is not
 the same as declaring these two direct input dependencies. In addition, every transpor
t role is bound in code to `gas_supply/price` as its `energy` cost multiplier, without
matching transport→gas dependencies in the PDL graph.

**How found:** compared dependency records, then traced merged dependencies through `_p
roducer_input_bindings()` and the literal `_ENERGY` recipe into `agent.binding` and `_e
ffects()`.

**Use:** fertilizer price shocks scale producer operating costs; gas-price shocks scale
 freight operating costs. Own-entity supply shocks are also mapped in code to the gener
ic `capacity` slot. This slot mapping supplies semantics beyond the raw PDL percentage.

**Evidence:** `s1-soja.roster.yaml:75–84`; `topology.py:68,226–231,308–329,385–410`; `m
odel.py:77–94`; `agents/base.py:36–40,83–89`; dependency farmer implementation lines 71
–78 and transport implementation lines 145–151.

## 2. Numeric calibration and behavioral assumptions

### 2.1 Operating costs and margins

**What is absent:** baseline costs and commercial margins are not in the shipped PDL. M
ost are class defaults in `scenario.py`, not columns in the shipped CSV:

| Role | Fixed operating cost per step | Margin |
|---|---:|---:|
| Brazil producer | 36,000 | 10% |
| Argentina producer | 42,000 | 10% |
| US producer | 48,000 | 10% |
| Wholesaler | 15,000 | 10% |
| Feed trader | 8,000 | 8% |
| Export-side land transport | 9,000 | 10% |
| Sea transport | 45,000 | 10% |
| Import-side land transport | 7,000 | 10% |
| Oil-mill processor | 20,000 | 12% |
| Feed manufacturer | 12,000 | 10% |

**How found:** compared PDL entity/impact fields with `SupplyChainScenario`, the CSV he
ader, and the `scenario_attrs` initialization recipes; verified consumption in installe
d agent pricing methods.

**Use:** turns production, handling, transport and processing volumes into unit prices
and establishes baseline supplier price differences. A new producer ID without ID-speci
fic attributes falls back to synthetic `fixed_costs_producer=1.0`, `margin_producer=0.1
0`, and `size_sigma_producer=0.0`; the PDL’s country/vulnerability does not supply a ca
librated fallback.

**Qualification:** `fixed_costs_eu_farmer=5,000` is also assigned, but the inspected co
nsumer step does not use it to price or determine output. It should not be represented
as an active livestock pricing model. Scenario comments describe costs as euros and qua
ntities as tonnes, whereas the metric catalogue deliberately uses generic currency/outp
ut units; the PDL provides no numeric unit contract for these calibrations.

**Evidence:** [scenario lines 27–81][scenario]; `topology.py:70–102,292–305`; `agents/t
ransport.py:19–21`; `db_schema.py:54–110`; installed agent pricing methods.

### 2.2 Baseline output, logistics/storage capacities, conversion ratios

**What is absent:** every producer gets `base_yield=100.0`; land transport gets capacit
y `500.0`; sea transport gets `1000.0`; wholesalers get storage capacity `2857.0` from
the scenario/CSV. Oil mills get conversion ratio `0.8`, feed manufacturing `1.0`, and l
ivestock output equals feed received numerically.

**How found:** compared entity data with literal `attrs` in roster recipes, the CSV, an
d dependency output calculations. The PDL’s strategic-reserve `capacity: "30-45d Verbra
uch"` describes an excluded buffer commodity, not wholesaler or port capacity. The PDL
does have an oil-market note saying approximately 80% meal/20% oil; the executable `0.8
` is hardcoded rather than parsed from that note. Thus the ratio is conceptually mentio
ned in the PDL, but not consumed as a parameter.

**Use:** determines baseline daily supply, bottlenecks, available stock, transformed qu
antities and downstream unit costs. The consumer feed→output factor is a modeling assum
ption shared across poultry/pig/dairy, not animal-specific production data from the PDL
.

**Important inactive fields:** sea `transit_steps=60` is assigned, but the inspected tr
ansport implementation does not use it to delay shipments; transport `utilisation_thres
hold=0.8` is a default with no decision use in that implementation. These are stored pa
rameters, not demonstrated travel-time/congestion behavior.

**Evidence:** `topology.py:74–93,222–231,403–410`; `scenario.py:19–23`; installed trans
port implementation lines 127–175, process implementation lines 40–67, farmer implement
ation lines 81–97.

### 2.3 Route weights and allocation rules

**What is absent:** `share_santos_port=0.7` and rules for distributing unspecified shar
es, splitting supply over peers/recipients, and admitting the cheapest incoming sea sup
ply first. PDL stages specify connectivity but not baseline flow weights or this market
-clearing behavior. PDL route-substitution coverage is a different quantity from baseli
ne port shares.

**How found:** followed `share_<entity>` collection in the transport adapter into `_rou
te_share()`; inspected `_admit_cheapest()` and the consumer `recipient_count` observati
on.

**Use:** normally splits Brazil exports 70%/30% between Santos and Paranaguá, normalize
s configured weights, and allocates constrained import handling by price. Consumers div
ide each source’s available feed equally across its active recipients. Producers are pe
rmanent baseline suppliers; PDL substitution coverage does not control their initial av
ailability.

**Evidence:** `scenario.py:16–17`; `agents/transport.py:23–42`; `model.py:121–128`; `ag
ents/farmer.py:22–27`; installed transport implementation lines 83–117,153–175 and farm
er implementation lines 85–88.

### 2.4 Size distributions, seed, survival state, and time horizon

**What is absent:** log-normal size spread parameters, deterministic seed `42`, a **365
-step** horizon, the CSV’s `run_num=1`, and a **21-day** zero-feed bankruptcy threshold
. The PDL’s event durations do not define the whole run’s length or a farm’s survival r
ule.

**How found:** compared the CSV and scenario defaults with PDL fields, traced farm setu
p’s seed-plus-agent-ID sampling, and checked zero-input counters in the installed consu
mer implementation.

**Use:** size factors scale producer output/costs; the seed makes this reproducible. Th
e zero-feed counter switches consumers inactive after 21 consecutive steps without feed
. The horizon limits all event execution and result series. Consumer size/cost fields a
re initialized, but the inspected consumer feed/output calculation does not weight allo
cation by size.

**Important execution detail:** with `--pdl`, `execution.py` copies the baseline CSV ro
w (`id=0`) to create the shocked row (`id=1`). The shipped baseline sigmas are zero, so
 nonzero sigmas in other template rows do **not** automatically apply to a PDL run.

**Evidence:** `scenario.py:49–60`; `data/input/SimulatorScenarios_template.csv:1–4`; `e
xecution.py:342–370`; installed farmer implementation lines 31–35,53–64,89–94.

### 2.5 Event interpretation and scenario selection

**What is additional:** code-defined worst-case aggregation (`supply=min`, `price=max`)
, neutral factor `1.0`, on/off shock scale `0/1`, one-shot expiration with no reactivat
ion, and selection of one cascade (the first if no selection is provided). The API/CLI
selection is separate from the PDL containing several cascades.

**How found:** compared the fields emitted by `to_event_registry()` with PDL fields and
 followed tracker aggregation and condition evaluation. PDL probabilities are not emitt
ed to the tracker; execution is schedule/condition driven rather than probability sampl
ed. `.active` evaluates as elapsed active days, so it is false on the activation day. T
hese semantics are implementation rules, not new PDL input values.

**Use:** determines how overlapping disruptions combine and when cascaded shocks actual
ly become effective. A maximum environment `shock_scale` is an activation indicator, no
t the magnitude of a price/supply shock.

**Evidence:** `pdl_loader.py:75–147`; `event_tracker.py:49–59,90–147,179–186,197–259`;
`shock_registry.py:14–20`; `environment.py:78–106`.

**Implicit baseline:** a PDL submission currently creates two scenario rows, unshocked
`0` and shocked `1`, even though the PDL does not request a baseline experiment. These
are separate scenario executions under one run ID, not two frontend POST requests. See
issue #64 below. Evidence: `execution.py:358–364`; `model.py:294–306`.

## 3. Geographic information and map semantics

### 3.1 Continents and sea-crossing classification

**What is absent:** the six-entry `LOCATION_CONTINENT` mapping for Brazil, Argentina, U
nited States, Netherlands, Germany and EU, plus the assumption that stages crossing kno
wn continents are sea routes.

**How found:** compared PDL `location` strings with `derive_sea_edges()`. The PDL has c
ountry/region names but no explicit continent or transport mode per stage. Sea carrier
IDs and their runtime instances are generated from these inferred crossings rather than
 declared as PDL entities.

**Use:** creates sea-transport agents, selects export/import handling recipes, wires th
e flow graph and sets exported `isSeaCrossing`. Unknown locations silently miss classif
ication; same-continent sea routes are not recognized by this proxy. These are current
limitations motivating #41.

**Evidence:** [topology lines 205–262][topology]; `topology.py:279–289,332–341`; `expor
t_bundle.py:178–219`.

### 3.2 Coordinates, localized labels, and illustrative-position flags

**What is absent:** all twelve modeled PDL entities lack `lat/lng/illustrative` values.
 The frontend gazetteer supplies them along with English marker labels. Examples: Brazi
l farms `(-13,-56)`, Santos `(-24,-46.3)`, oil mills `(52,4.5)`, and separate illustrat
ive livestock placements. The four added traders obtain illustrative coordinates from t
he sidecar instead.

**How found:** checked every PDL entity for coordinate fields and compared IDs with `GA
ZETTEER`; followed `_entity_placement()` through bundle nodes to `resolveScene()`. Decl
ared PDL/roster placements take precedence over the fallback. Fallback marker labels ma
y differ from PDL names; node/edge labels are assembled from entity names by the export
er.

**Use:** locates map markers, positions edge endpoints, supplies marker text, and marks
 chosen approximations. Unknown entities without declared coordinates or gazetteer entr
ies are omitted with a warning; there is no automatic country-centroid placement. These
 coordinates do not determine transport duration or freight costs.

**Evidence:** [gazetteer lines 38–58,111–172][gazetteer]; `s1-soja.roster.yaml:30–59`;
`export_bundle.py:97–175`. Open issue #25’s [comment](https://github.com/PROVIDER-Proje
ct/simenv/issues/25#issuecomment-6036871279) independently confirms the twelve-versus-f
our placement split.

## 4. Generated results and operational data used beyond PDL inputs

### 4.1 Agent state, macro indicators, and metric definitions

**Additional data:** node series for `quantity_available`, `unit_price`, `active`, `sto
rage_utilization`, `feed_received`, and `livestock_output` as applicable; environment s
eries for soy/feed price, total soy supply, transport utilization, shock activation, dr
ought severity and step. Internal state also includes stock, conversion input, size fac
tor and days without feed.

**How found:** enumerated `_PROPS_BY_ROLE` and `ENVIRONMENT_PROPS`, traced environment
calculations and database metric definitions, and compared them to PDL impact percentag
es. The PDL states perturbations; these are computed outcomes or runtime state, not mis
sing baseline input fields.

**Use:** writes CSV/PostgreSQL results, supplies external stepwise snapshots, powers pl
ayback and headline values. Soy/feed prices are volume-weighted means across wholesaler
s/feed traders; total supply sums producers; transport utilization is an arithmetic mea
n. Recording is selected by code, not PDL: port/sea agents run but have no individual r
ecorded series.

**Evidence:** `data_collector.py:19–35`; `environment.py:128–211`; `db_schema.py:54–112
`; `model.py:350–374`.

### 4.2 Exported JSON graph/result contract and aggregation metadata

**Additional data:** `nodes`, `edges`, `ticks`, `env`, node `role/entityIds/placements/
hasRecordedData`, edge IDs and `isSeaCrossing`, and metadata `pdl/scenario/ticks/genera
tedAt/honestyNote`.

**How found:** compared [frontend bundle types][types] with exporter construction and i
ts aggregation rules. The exporter sums extensive quantities, averages prices/utilizati
on, uses any-active for activity, rounds values to four decimals, and collapses sea age
nts into endpoint-to-endpoint map edges. This graph reflects the executable roster/side
car, not the complete unfiltered PDL graph. `meta.scenario` is generated as `scenario_<
number>`, not copied from the PDL’s scenario ID.

**Use:** gives the browser a ready-to-play graph and time series. The main app fetches
`/bundle.json`; it does not simulate from PDL or query PostgreSQL directly. API complet
ion does not automatically replace the loaded globe bundle.

**Evidence:** `export_bundle.py:50–55,146–219,234–252,321–381`; `web/src/main.tsx:1–12`
; `web/src/data/staticJsonSource.ts:135–143`; `web/src/configurator/SimulationRunner.ts
x:84–94`.

### 4.3 Run identity, provenance, lifecycle, progress, and service configuration

**Additional data:** generated timestamp/UUID run ID, start/end timestamps, status, PDL
/roster hashes, Git SHA, label, executed numeric scenario IDs, horizon, output/job path
s, errors, per-scenario and overall step counts, and percentage completion. API URL/dat
abase connectivity are deployment settings outside the PDL as well.

**How found:** compared `run_record()` and `PreparedRun` with frontend submission/job i
nterfaces, progress serialization and export provenance checks. PDL `scenario.id` ident
ifies a scenario definition; it is not the execution/run ID. `cascade` and `label` are
separate request fields alongside PDL and roster text.

**Use:** associates recordings with the correct execution, tracks background jobs, sele
cts historical outputs, and prevents pairing recorded values with changed PDL/sidecar f
iles. These are execution/service concerns rather than additional supply-chain facts. C
urrent provenance records Git HEAD but not the actual resolved external-agent commit or
 a complete calibration snapshot, so the PDL hash alone does not describe all behavior-
affecting inputs.

**Evidence:** `run_registry.py:62–104`; `execution.py:38–48,191–245,395–442`; `web/src/
configurator/simulationApi.ts:1–24`; `export_bundle.py:69–90`; `db_config.py`; `pyproje
ct.toml:7–11,40–42`.

## 5. Frontend-only interpretation and editor information

### 5.1 Derived disruption intensity and animation data

**Additional information:** the browser assigns “stress” using price first, otherwise n
egative livestock output, otherwise negative available quantity, then min–max normalize
s each node across the whole loaded run. Flat/missing series have zero intensity. Edge
intensity uses the source node’s intensity, falling back to the target only when the so
urce has no entry. The globe quantizes intensity in `0.1` increments.

**How found:** traced `buildDynamics()` into the globe’s color/radius inputs; compared
those formulas with PDL vulnerability and impact severity fields. These intensities are
 not read from PDL vulnerability/severity or recorded edge flows.

**Use:** drives red tint and marker growth. Animation dashes have fixed visual timing;
they are not measured tonnage, shipment velocity, money flow, or an absolute comparable
 resilience metric. Playback currently advances every 60 ms. Other external presentatio
n data include globe textures, camera settings, colors, label geometry and a hardcoded
Brazil marker highlight.

**Evidence:** [dynamics lines 28–85][dynamics]; `web/src/globe/GlobeView.tsx:8,47–50,83
–109,173–206,224–239,266–296`; `web/src/App.tsx:12–13,61–74`; `web/src/design/tokens.ts
`.

### 5.2 Scenario editor presets, control limits, and generation policy

**Additional information:** the editor’s draft configuration, exposed cascade choices,
labels, default values, control bounds, relative timeline offsets, enable/disable switc
hes, and bundled PDL/roster templates. For example, the drought-loss slider is limited
to 5–90%; only soy and energy cascades are selectable even though the shipped PDL also
contains `compound_crisis`.

**How found:** compared `defaultScenarioConfig`, timeline-offset constants and slider b
ounds with PDL events/cascades; followed `buildPdl()` and `buildRosterSidecar()`. Many
default magnitudes/days duplicate PDL values, so they are duplicated configuration rath
er than genuinely missing domain facts. The UI limits and generation policy are extra a
pplication rules.

**Use:** builds a new runnable PDL plus sidecar. Enabled/disabled state becomes retaine
d/removed timeline entries/events, and the generated document retains only the selected
 cascade. Dependent conditions/causes are sanitized. Values written into the generated
PDL are then specified there; the separate roster still carries the extra topology. The
 configurator initializes from bundled presets, not a reconstruction of all inputs that
 produced the displayed run.

**Evidence:** `web/src/configurator/pdlTemplate.ts:1–139,202–223,252–335,346–453`; `web
/src/configurator/ScenarioConfigurator.tsx:68–87,136–138,156–201`.

## 6. Open issues: potential future differences and current status

These are possibilities indicated by issue text, not promises of a particular future sc
hema. The issue set was read live on the audit date; implementation status below refers
 to the inspected checkout.

### Highest-relevance domain/model changes

| Open issue | Potential future data change | Comparison with current implementation |
|---|---|---|
| [#41 Declare geography and sea-crossing classification in data](https://github.com/PR
OVIDER-Project/simenv/issues/41) | Proposed sidecar `geo` block keyed by entity ID with
 `continent/lat/lng/illustrative`, plus `crossings: [{stage: [a,b], mode: sea\|land}]`.
 Would move current hardcoded geography into additional declared data and add explicit
transport mode. | Not present in current `RosterSidecar`; hardcoded `LOCATION_CONTINENT
` remains. Issue explicitly leaves frontend migration to #25/#33. |
| [#25 Load supply chain from PDL and display it on world map](https://github.com/PROVI
DER-Project/simenv/issues/25) | Coordinates for every entity, potentially PDL fields or
 a sidecar placement section; final shape is undecided. | Topology and exporter placeme
nts already exist. The comment narrows remaining work to the twelve modeled PDL entitie
s still using gazetteer fallback. |
| [#8 Read entity parameters from PDL](https://github.com/PROVIDER-Project/simenv/issue
s/8) | PDL vulnerability-driven costs/capacities/behavior or explicit calibration field
s could replace external defaults. A vulnerability-to-parameter mapping itself would ne
ed defined semantics. | Vulnerability exists in PDL but is not consumed by current topo
logy/adapter setup. Counts are now one agent per roster entry, so the issue’s old claim
 about CSV counts is stale. |
| [#45 Consumers ignore PDL impacts aimed at them](https://github.com/PROVIDER-Project/
simenv/issues/45) | May add livestock output/capacity semantics, consumer prices and re
corded price metrics; any size/criticality-based feed weighting would introduce additio
nal policy/data needs. | Consumer capacity effects are passed but not used in the insta
lled consumer step, and no consumer price is produced. The issue’s separate shared-upst
ream allocation bug is already addressed here through per-source `recipient_count`; do
not report that part as still present. |
| [#6 Add substitution logic](https://github.com/PROVIDER-Project/simenv/issues/6) | Ru
ntime substitution coverage, activation thresholds, ramp-up progress, cost/quality chan
ges, depletion, side effects and dependency overlap may become consumed data/state. Mos
t input fields already exist in the PDL, so this mainly closes a consumption gap rather
 than necessarily adding new input fields. | Current loader has no substitution parser;
 agent step inputs do not carry substitution definitions. Supply activation events are
not equivalent to implementing the PDL substitution contract. |
| [#19 Generalize port routing with origin allow-list](https://github.com/PROVIDER-Proj
ect/simenv/issues/19) | The proposal mentions explicit `accepted_origins` and an origin
→reporting-region map, which would be external routing/reporting data unless declared i
n PDL. | Current code instead uses graph-based regional wholesalers and generic route w
eights, without the old `exclude_*` or named region-volume fields. The issue’s proposed
 allow-list is not evidence of current allow-list data. |

### Execution, exchange, and visualization changes

| Open issue | Potential future data change | Current evidence / qualification |
|---|---|---|
| [#60 External run IDs](https://github.com/PROVIDER-Project/simenv/issues/60) | Caller
-supplied execution/correlation identity persisted across API/database/results, separat
e from PDL scenario ID. | IDs are currently generated by `_reserve()`/`new_run_id()`; t
he frontend submission has no external-ID field. |
| [#53 Provenance without `--pdl`](https://github.com/PROVIDER-Project/simenv/issues/53
) | Record resolved default PDL provenance or store full PDL/roster text in `sim_run`;
the second option changes stored data/schema. | Standalone topology uses the default PD
L, while `run_record(pdl=None)` records null path/hash. The issue has not selected betw
een its two options. |
| [#59 Bundle results after completion](https://github.com/PROVIDER-Project/simenv/issu
es/59) | Automatically produced JSON run/result artifact for cross-component exchange;
possibly broader than the existing single-scenario visualization bundle. | Manual expor
ter exists, but `_execute()` ends by marking completion, without exporting a bundle. Ex
act “all run data” format is not specified by the issue. |
| [#64 One simulation per API call](https://github.com/PROVIDER-Project/simenv/issues/6
4) | Changes scenario cardinality, baseline selection and progress/result metadata. A b
aseline option may need an explicit API/control representation; the issue does not pres
cribe one. | Backend currently creates baseline and shocked rows; progress validation a
ssumes two scenarios. No evidence that the frontend sends two POST requests. |
| [#24 Animated goods/money streams](https://github.com/PROVIDER-Project/simenv/issues/
24) | If animations must quantitatively represent flows, per-edge goods and monetary tr
ansfer series plus units would be needed. This is an inference about requirements, not
an explicit issue schema proposal. | Current animation depicts inferred stress, with fi
xed dash timing. Bundle edges have topology/mode but no per-edge flow series; ports/sea
 agents have no individual recorded series. |
| [#27 Simulation playback](https://github.com/PROVIDER-Project/simenv/issues/27) | His
torical-run catalogue/selection and playback-speed state beyond PDL; possible bundle/ru
n identity linkage. | Step seeking and play/pause already exist. Main app still loads o
ne static bundle; run selection and configurable playback speed are not implemented the
re. |
| [#22 Parameter configuration UI](https://github.com/PROVIDER-Project/simenv/issues/22
) | More exposed parameters/presets could create additional editor metadata; scenario-s
pecific domain values should be checked for serialization into PDL versus sidecar/engin
e configuration. | First-pass PDL/roster generation already exists. The issue does not
specify new missing parameter fields. |
| [#54 Retention/deletion](https://github.com/PROVIDER-Project/simenv/issues/54) | Cons
istent deletion across run index/database; possible later labels/retention policy metad
ata. | Operational lifecycle work, not a new supply-chain input. “Keep last N/keep labe
lled” is explicitly later scope. |

### Other open issues checked

- [#7 Dynamic topology](https://github.com/PROVIDER-Project/simenv/issues/7): PDL/sidec
ar-derived roster and wiring already exist. The current extra graph data is documented
in section 1; this issue is not evidence that routing is still entirely hardcoded.
- [#5 Event duration](https://github.com/PROVIDER-Project/simenv/issues/5): duration pa
rsing and expiration are implemented; no new absent duration field is required by the i
ssue.
- [#18 Stepwise execution](https://github.com/PROVIDER-Project/simenv/issues/18): both
loops now share `_do_step()` including tick recording, though `run()` does not literall
y delegate to the generator. Possible future RL observations/actions are an integration
 direction, not a defined new domain dataset.
- [#62 Agent extraction](https://github.com/PROVIDER-Project/simenv/issues/62): extract
ion/wrappers/dependency are already present on this checkout. The issue explicitly asks
 for no behavior changes; it does not itself propose new PDL data. It makes the resolve
d external agent version important for reproducibility.
- [#57 Agent-list mapping](https://github.com/PROVIDER-Project/simenv/issues/57): conta
iner/namespace refactor and reserved `environment` identity; no new supply-chain data p
roposed.
- [#30 Remove `effective` from agent interface](https://github.com/PROVIDER-Project/sim
env/issues/30): title only; no new data contract can be inferred. Current adapters alre
ady pass resolved effects into standalone agent inputs.
- [#55 Tooling hygiene](https://github.com/PROVIDER-Project/simenv/issues/55), [#65 Pla
yback UI layout](https://github.com/PROVIDER-Project/simenv/issues/65), and [#21 Visual
ization framework](https://github.com/PROVIDER-Project/simenv/issues/21): no domain-dat
a addition specified. Layout/collapse state and tooling versions are application/develo
pment concerns.

## 7. Distinguishing missing inputs from unused PDL information

The opposite direction matters when interpreting the gaps:

- **Already specified but not operationally consumed:** vulnerability scores; substitut
ion definitions; event/cascade probabilities; `demand` impacts; much dependency critica
lity/metadata and cascade `affects`; several excluded downstream/resilience entities. T
he loader only emits supply/price impacts and `at/event` timeline fields, so these are
not evidence that such data is absent from PDL.
- **Partially wired:** consumer-targeted supply/price shocks are tracked, but do not ch
ange consumer output/price in the inspected implementation. Processor energy disruption
 is represented through its supply event; the declared oil-mill gas dependency is not a
 general processor energy-cost binding.
- **Already modeled today:** four sidecar traders, their graph insertions, per-entity c
onsumers, event expiration and dynamic topology. README lines 7–9/243–247 and some fron
tend type comments still describe older behavior. The report uses executable paths rath
er than those comments as the deciding evidence.
- **Stored but inactive:** the sea transit and transport utilization-threshold fields a
bove should not be counted as working travel-time or congestion models.

## Bottom line

To reproduce the current simulation and its displayed interpretation, the PDL alone is
insufficient. At minimum the effective specification includes the **PDL + roster sideca
r + scenario CSV/class defaults + topology/binding rules + resolved agent implementatio
n**. Display reproduction additionally requires **placements/gazetteer + result bundle
+ frontend interpretation rules**. Run IDs, progress and provenance belong to the execu
tion/result contract rather than to the supply-chain description itself.

For a future PDL/schema discussion, prioritize explicit actor roles and graph additions
, calibration/units, geography/transport modes, and consumer/substitution semantics. Ke
ep computed outputs and operational metadata identifiable as separate contracts rather
than treating every non-PDL field as a missing domain input.

## Source links

Links below are pinned to the inspected simenv commit. For abbreviated `path:line` cita
tions, Python module paths such as `topology.py` and `agents/base.py`, and `data/input/
...`, are relative to `/data/home/repositories/simenv/src/provider_simenv`; bare scenar
io YAML filenames are in that package's `scenarios/` directory. Paths beginning `web/`,
 `README.md`, and `pyproject.toml` are relative to `/data/home/repositories/simenv`. Ex
ternal-agent references such as `provider-agents/offis_agents/...` mean `offis_agents/.
..` under `/tmp/opencode/provider-agents-62/src/provider_agents`.

[pdl]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce71b7fb
e8532ab8/src/provider_simenv/scenarios/s1-soja.pdl.yaml
[roster]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce71b
7fbe8532ab8/src/provider_simenv/scenarios/s1-soja.roster.yaml
[topology]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce7
1b7fbe8532ab8/src/provider_simenv/topology.py
[scenario]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce7
1b7fbe8532ab8/src/provider_simenv/scenario.py
[gazetteer]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce
71b7fbe8532ab8/web/src/data/gazetteer.ts
[types]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce71b7
fbe8532ab8/web/src/data/types.ts
[dynamics]: https://github.com/PROVIDER-Project/simenv/blob/d3146f33b582220362539a43ce7
1b7fbe8532ab8/web/src/playback/dynamics.ts
