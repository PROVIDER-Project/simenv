# Extract standalone PROVIDER agents

## Purpose and approved scope

Implement simenv issue #62 across `PROVIDER-Project/simenv` and
`PROVIDER-Project/provider-agents`. Move all internal agent logic into
`provider-agents`, using its existing `AbstractPROVIDERAgent` contract.
Keep only framework wrappers and adapters in simenv. Preserve existing
simulation behavior, including seeded results and observable agent state.

The user explicitly confirmed that the example farmer in provider-agents
is not a compatibility requirement. The current simenv implementations
are the behavioral reference. Every new concrete implementation must
include the `AgentSpec` required by the contract, with schemas for setup
input, setup output, step input, and step output.

Deliverables include a companion issue in provider-agents, changes on new
branches, and linked pull requests in both repositories.

## Architecture

### Standalone agent package

Provide `FarmerProviderAgent`, `TraderProviderAgent`,
`ProcessProviderAgent`, and `TransportProviderAgent` under
`provider_agents.offis_agents`, with documented public imports.
Each subclasses `AbstractPROVIDERAgent` and implements `_setup` and
`_step`; callers use the validated public `setup` and `step` methods.
Replace the illustrative farmer implementation with the migrated one.

The package owns defaults, derived initialization, size sampling, role
dispatch, arithmetic, pricing, equal-share allocation, storage limits,
conversion, bankruptcy, route-weight normalization, transport mode
selection, and cheapest-first admission. Shared internal helpers may
remove repetition without changing arithmetic or evaluation order.

Standalone agents receive and return ordinary dictionary data: numbers,
strings, booleans, lists, and nested records. They never receive Melodie
agents, AgentLists, model/scenario objects, framework callbacks, or PDL
loader objects. There is no dependency on simenv or Melodie.

Retain NumPy for the existing `default_rng(seed + id).lognormal(...)`
algorithm. Switching random-number generators would change behavior.

### Simulation adapters

Preserve the existing `provider_simenv.agents` classes and role exports
so topology construction and existing imports continue working.
Wrappers retain Melodie inheritance and the framework-facing lifecycle
(`setup`, parameter assignment, `post_setup`, and `step`).

Wrappers translate roster entries, adjacency, scenario values, resolved
shock multipliers, active upstream records, and peer membership into
the standalone contract. They apply returned state to ordinary wrapper
instance attributes so Melodie collectors continue seeing it.

Only data extraction and application live in these wrappers. In
particular, wrappers must not retain pricing formulas, random sampling,
bankruptcy rules, route normalization, cheapest-first sorting, or
decision-making branches. They may resolve framework identities and
classify framework objects into explicit input metadata.

Standalone implementations expose the optional host helper
`requires_observations(state)`. Wrappers query it before gathering framework
observations so inactive and unknown-role paths do not require topology
wiring. The helper owns this role/activity decision; the validated public
step method still produces the original no-op or error.

## Lifecycle and state synchronization

Use the standalone agent as the owner of internal behavioral state.
Its setup produces initialized state; wrappers publish that state on
their own instances. Framework setup must still expose the fields
required before model parameter assignment. Obtain initial defaults
from the standalone implementation, then initialize with assigned
parameters at `post_setup`; do not sample size twice or rescale already
scaled values.

Before stepping, adapters synchronize externally mutable state into the
standalone agent through explicit dictionary inputs. This includes
market activity and state changed by downstream transport admission.
Do not reset the agent by calling setup on every step: that would repeat
initialization and lose bankruptcy counters or rescale farm sizes.

Only fields actually updated by the selected path are returned as state
patches and applied. Inactive agents return no changes. Preserve existing
path-specific behavior, including stale prices where the old early-return
path leaves them untouched.

Bindings and entity/list identities remain framework metadata. Adapters
resolve semantic slots with the current absent-binding default of 1.0;
standalone agents consume the resulting multipliers. The model may attach
capacity bindings after `post_setup`, as it currently does.

## Contracts and AgentSpecs

Each class declares a versioned `AgentSpec` with a stable archetype id,
description, and all four schemas. Declare properties and required keys
for each documented message, nested source records, and output patches.
Document supported roles and explicitly describe optional values and defaults.
Role schemas accept strings so original unknown-role errors/no-ops occur
during dispatch rather than being replaced by schema errors.
Validate messages via the existing public contract methods, not by
bypassing them in adapters.

Setup inputs describe the role, behavioral parameters, initial mutable
state, and any seed/id needed for initialization. Setup outputs describe
all initialized behavioral fields. Step inputs describe external state
updates, resolved effects, peer counts, upstream records, and routing
metadata required by the class. Step outputs describe changed local
state and, for transport admission, upstream state updates.

Schemas must model existing accepted simulation inputs and possible
outputs. Do not add positivity constraints or new mandatory values that
reject otherwise supported simulations. Inactive no-op results and each
role's partial update shape must be valid. Test schema validation with
jsonschema installed, and exercise the contract's fallback mode. Contract
tests must not assume the fallback enforces full JSON Schema semantics.
Nested schemas require capacity for transport sources and base yield when
the input state identifies a wholesaler. When the wholesaler role is retained
from setup rather than repeated, execution checks that requirement explicitly.

## Agent-specific behavior

### Farmer

Preserve both producer and consumer roles, size-factor sampling, scaled
fixed costs and yield, cost-based initial prices, capacity/fertilizer
effects, feed sharing across all active consumers, and bankruptcy timing.
The adapter gathers active consumer counts and upstream feed quantities;
the agent computes the result. Preserve the currently accepted optional
`drought_severity` wrapper step argument, which has no behavioral effect.

### Trader

Preserve wholesaler and feed-trader roles, markup initialization, upstream
weighted prices, equal allocation, storage constraints and utilisation.
Adapters resolve the correct list and peers, including the existing
wholesaler membership fallback. Calculations belong in provider-agents.

### Process

Preserve processor and feed-manufacturer roles, active-input handling,
peer sharing, conversion yield, capacity effects, and input-cost pricing.
Adapters resolve upstream and peer lists; standalone code calculates all
state updates.

### Transport

Adapters serialize the relevant graph and entity/route metadata, scenario
route weights, upstream states, source type metadata, peer counts, and
resolved effects. Standalone code selects export split, ordinary movement,
or multi-source cheapest-first admission using that metadata.

Preserve route weight defaults, validation, normalization, capacity and
energy effects, margin, equal peer splitting, stable price sorting, and
the existing demand-target calculation. Preserve current behavior of
transit-related fields without introducing delayed delivery.

Admission returns source patches identified by stable input record keys.
The wrapper maps those keys back to the original upstream objects and
applies quantity and transport-utilisation changes in the same step.
Source prices remain untouched. No live source objects cross the package
boundary, and no allocation or utilisation arithmetic remains in simenv.

## Dependency and repository coordination

Add provider-agents as a normal runtime Git dependency of simenv targeting
the `main` branch, and update `uv.lock`. During development, resolve the
unmerged implementation locally using an uncommitted local checkout
override. The committed dependency declaration must target `main`, not
the development branch or an implementation commit. Do not commit local
path overrides. A Git revision recorded by the lockfile is the normal
resolved snapshot of the declared main-branch dependency; refresh it
against main once the provider-agents changes merge. Ensure package
metadata supports the stated Python >=3.10 baseline, including imports
used by the migrated implementation.

Create the companion issue and implementation branch in provider-agents.
Link that issue and simenv #62 in both pull requests, explaining that the
agent package change should merge first. Keep the work scoped to this
extraction and its contracts, packaging, documentation, and verification.

## Errors and compatibility

Preserve role-specific error/no-op behavior and route-weight failures.
Keep the existing simulation execution order and floating-point operation
order. Wrapper mapping errors should surface rather than silently dropping
source updates. Contract-validation failures propagate to the caller.

No new transport, economic, shock, or bankruptcy behavior is introduced.
The existing example farmer's random sampling and schema restrictions do
not override compatibility with simenv.

## Verification and acceptance criteria

Before replacing simenv implementations, record deterministic reference
traces of collected behavioral fields for every agent, including initial
state and intermediate steps. Cover the shipped scenario with and without
disruptions, alternate topology, nonzero size variation, constrained
cheapest-first admission and route splits, consumer starvation through
bankruptcy, and empty/inactive inputs. Fixtures record numeric/state data,
not a second maintained copy of the old algorithm.

Standalone tests verify all four public contracts and required AgentSpecs,
initialization, representative role outputs, partial/no-op updates, state
continuity, transport source patches, and documented errors. Verify these
agents run without importing simenv or Melodie.

Adapter integration tests compare post-migration per-agent traces to the
pre-migration reference, including upstream mutations and seeded initial
values. Existing routing/topology tests remain relevant regression checks.
Run both repositories' test suites and relevant configured static checks;
report pre-existing failures separately if discovered.

Completion requires all four implementations and their AgentSpecs in
provider-agents, adapter-only agent modules in simenv, a reproducible
dependency, behavior-equivalence evidence, documentation, the companion
issue, and both pull requests.
