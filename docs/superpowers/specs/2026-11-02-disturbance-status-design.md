# Explainable workshop disturbance status (#75)

## Intent and scope

Workshop participants configure disturbances, submit a simulation, open its exact
recorded results, and inspect where prices, availability/output and pressure
worsen or recover. Status must explain evidence without changing raw values.
Database playback and the static exported demo remain supported. This is a
frontend-only change using the existing paged source and frame buffers.

## Architecture

- `playback/status.ts`: pure, role-aware metric registry, fixed thresholds,
  evaluations, deterministic severity/coverage aggregation and explanations.
- `playback/reference.ts`: reference policy, canonical structural compatibility,
  exact `(entity_id, agent_id, role)` matching and period coverage validation.
- `playback/frame.ts`: one display projection for nodes, source-inherited edges,
  and the four environment indicators. Join recordings to `Node.id`, not its
  geographic `entityIds`. Keep measurements immutable and precision intact.
- `referenceLoader.ts` owns a separate bounded buffer, compatibility checks and
  settled reference failures. `usePlayback` pins the first frame, owns lifecycle
  cancellation and atomically publishes matching current/reference snapshots.
- Shared status colors, legend, reference selector, component list/details and
  timeline consume the projection. Selection rings and illustrative-placement
  annotations are independent of status fill.
- App/configurator/runner provide exact completed-run selection and submitted
  snapshot versus next-run edit messaging. Sources explicitly declare mode.

## Metric policy

Producers: price, quantity and recorded participation. Wholesalers: price,
quantity and storage/handling pressure. Processors/feed manufacturers: price,
quantity, and optional status-driving relative decreases in `input_received`
(Input offered) and `input_processed` (Input processed). Feed traders: price
and quantity. Consumers: feed received, livestock output and participation.
Environment: soy price, feed price, total soy supply and transport utilization.
Unrecorded ports/routes have unavailable measured status. `unused_input` is a
diagnostic only. Do not infer unmet demand or production utilization.

Relative prices worsen upward; availability/output worsen downward. References
must be finite and positive. Zero output with a positive reference is a 100%
decline. Zero/missing references are unavailable, never healthy. Zero prices mean
no quote and are unavailable, not beneficial recovery. Inactivity is red without
requiring a reference. Capacity uses absolute fractions. Optional historical
diagnostics absent on both sides do not make older recordings incomplete. A
status-driving diagnostic present on only one side is an unavailable comparison
and contributes to incomplete coverage.

Illustrative workshop defaults, centralized for future domain calibration:

- Relative adverse change: green through 5%; interpolate to amber at 20%, then
  to red at 50%; saturate thereafter. Improvements are green.
- Capacity: green below 80%; amber at 80%, interpolate to red at 95%.
- Labels: green = near reference / low pressure; intermediate green-to-amber
  changes = increasing; amber-to-red = elevated; red = severe; gray = unavailable.

Evaluate all applicable metrics. Strongest metric determines agent status;
strongest agent determines node status. Stable registry order and sorted agent
identity resolve ties. Coverage is complete, partial or unavailable. Known
adverse evidence remains visible with incomplete coverage; green-only evidence
with missing applicable comparisons is gray. Missing expected agents (using the
first frame census) are explained. No claim is made about agents absent from
every frame. Multiple placements share the same pooled-node assessment.

## Reference policy and synchronization

Default to same-run scenario 0 at corresponding periods, when catalogued;
otherwise use **Relative to scenario start**. Start means the first recorded
end-of-step frame, which may already contain a day-0 disturbance. Pin it outside
the evictable page cache. External reference selection offers completed playable
runs containing scenario 0, never labels scenario 1 as unshocked.

External references must have matching canonical nodes (IDs, roles, represented
entities, recording flags), directed edges/sea classification, exact recorded
identities and sufficient period coverage. Ignore labels, coordinates, ordering
and filenames. Validate identities each period. Explain incompatibility, missing
metrics/periods and request failures; never silently fall back. State that
structural compatibility does not verify economic configuration equivalence.

Retain the complete displayed pair during current/reference buffering for the same
generation, including seeking; suspend advancement until both requested frames
are ready. Cache hits do not become unavailable/loading states. Recorded scenario-0
references must match the displayed period; scenario-start references always
remain at the first recorded period. Both must belong to the active selection
and reference generation. A source/reference-generation change or actual reference
error makes relative comparisons unavailable immediately, while capacity
and participation still work. All indicators, details and globe colors consume
that same projection. Reject late responses after seek/run/scenario/reference
changes even if transport cancellation is ignored. Reference errors have a
separate retry action and remain settled until explicit retry. Prefetch both
streams. Validate HTTP scene response identities as well as pages. Fixed indicator
grid cells, tabular numbers and reserved status/detail rows prevent playback text
from shifting layout; long explanations remain accessible.

## Interface and workshop loop

Compact legend explains colors, thresholds, worst-agent aggregation and
**inferred upstream status** on connections. Connections inherit only their
source node; unknown sources remain gray, without target fallback or invented
local transport utilization. The timeline shows soy/feed prices, soy supply and
average transport utilization with values, textual status and explanations.

A keyboard-accessible native component selector includes unplaced/unrecorded
nodes and shares selection with globe clicks. Details show name, step, overall
status, responsible metric and agent, coverage, all applicable current/reference
values, percentage changes/capacity, diagnostics and reference explanations.

Capture submitted PDL/roster/cascade/label at submit time. Explain later edits as
next-run inputs. After completion, **View results** resolves that exact ID across
catalogue pages and selects scenario 1, without newest-run substitution or
refresh races. Static mode explains the need for recorded-playback configuration.
Keep displayed recorded run/scenario visibly separate from configurator inputs.

## Alternatives considered

1. Browser-side pure evaluator and separate reference buffer (selected): preserves
   the source contract, testability and cache-independent raw-data fidelity.
2. Backend-computed status: adds payload/API coupling and cannot help static demo.
3. Run min/max or first available metric: inconsistent cross-run meaning and
   conceals simultaneous availability declines; rejected by the issue.

## Verification and documentation

Unit coverage: thresholds, interpolation/recovery, simultaneous metrics, zero
references/prices/output, inactivity, role semantics, partial/multi-agent
aggregation and ties, identity/structure/period mismatches, day-0 disturbance,
immutability, source-only links and cache-independent start references.
Browser coverage: keyboard inspection, seek/reference/run switching and stale
responses, reference retry, exact results opening, edited-input messaging,
static mode and mobile usability. Real simulation acceptance uses scenario 1.
Run required Python regressions (including isolated PostgreSQL integration where
available), frontend install/typecheck/lint/build, playback unit/browser and
simulation acceptance checks. Record skips/blockers accurately. Capture before
and healthy/disturbed/recovered/unavailable screenshots for PR review.
Update README workshop summary, web README and playback guide with these rules.

## Review

An independent subagent reviewed the issue, code, docs and proposed architecture.
Its semantic, partial-coverage, compatibility and synchronization refinements
are incorporated here. User delegated decision-point approvals to independent
reviewers. No unresolved product ambiguity remains; threshold calibration and
external economic equivalence are explicitly described limitations.
