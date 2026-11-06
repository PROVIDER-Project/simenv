# Frontend-managed disruption-free references

## Intent

Recorded playback defaults to a compatible experiment with no disruptions. The
frontend searches persisted runs and active jobs, explicitly submits a separate
empty-events job when necessary, and waits for playable data before displaying
the comparison. The simulation API continues executing exactly one scenario per
submission; no implicit baseline execution is added. The workshop configurator's
active cascade is fixed to `soy_crisis_cascade`; soy parameters remain editable.

## Minimal contracts

Add read-only `GET /simulations/{id}/inputs`. Return JSON-compatible parsed
`pdl`, `roster` (null when absent), resolved `cascade`, preserved row-0
`parameters`, current submission-default `current_parameters`, and `evidence`
(`preserved` or `execution-hashes`). Exclude scenario IDs from parameter maps,
but retain duration, run count, seed and every other engine parameter.

Check job membership before filesystem paths. Unknown jobs return 404; missing,
modified, corrupt or non-JSON-compatible preserved inputs return 409. Verify exact
PDL/roster bytes against the execution manifest when available, preserving absence
of a roster as evidence. Corrupt manifests are not missing manifests. Completed
jobs require their execution manifest and executed CSV; compare executed scenario
1 parameters with the copied row-0 template. Queued jobs can expose preserved
inputs before execution hashes exist. Template integrity is bounded by these
consistency checks, not a historical hash guarantee. No credentials or internal
paths are returned. No POST, queue, database-schema or execution behavior changes.

## Reference identity and recipes

Recorded references carry `{runId, scenarioId, evidence}`. Evidence distinguishes
scenario-zero event bypass from an API scenario with verified empty event
definitions and an empty selected timeline. Arbitrary scenario 1 is never eligible.
Keep manual scenario-0 and explicitly labeled scenario-start options.

To build an unshocked submission, copy parsed PDL/roster; normalize scenario name
to a fixed reference name; replace events with `[]` and cascades with one declared
`unshocked_reference` cascade containing `timeline: []`. Preserve non-event model
declarations and all roster economics. Submit JSON text (valid YAML), with the
same roster absence/presence. A stable recursive serializer sorts object keys,
preserves array order and includes normalized documents plus engine parameters.
Names/comments do not identify a baseline; verified inputs do.

## Frontend lifecycle

Use a source-scoped coordinator outside component lifetimes. It owns discovery,
recipe-key deduplication, accepted job IDs, monitoring and explicit retry. Register
entries synchronously before asynchronous work, so StrictMode/effect cleanup and
selection remounts cannot duplicate submission. React subscribers detach on
selection changes; accepted backend work continues and can be reused.

1. Load selected scene/initial identities and exhaust playback catalogue pages.
2. Prefer a compatible same-run scenario 0, then compatible external scenario 0.
   Validate structure, period coverage and initial identities before accepting;
   skip incompatible candidates and continue searching.
3. Read selected preserved inputs; scan scenario-1 database candidates and active
   API-job history for verified empty-event inputs with the same recipe. A queued
   or running match is monitored, not submitted again.
4. Discovery/network failures are errors, never proof that no baseline exists.
   Deduplicate IDs and refresh the newest job page before creating after a long
   search. Automatic creation requires the selected parameters to match current
   POST defaults. Historical CLI runs with scenario 0 remain supported; recordings
   without usable references or preserved inputs explain their reproduction limit.
5. Frontend POSTs the missing reference. Re-read its accepted preserved inputs to
   catch defaults changing between preflight and submission. Revalidate attached
   jobs after completion. Wait for completed/playable catalogue visibility, not
   merely 100% progress; then validate scene/identity compatibility again.
6. Expose discovering/submitting/queued/running/awaiting-playback/ready/error
   states. While preparing, no scenario-start comparison is silently displayed.
   Explicit start mode remains available; static demo never creates jobs.
7. Monitor/retry an accepted ID without resubmission. Ambiguous POST outcomes are
   latched: retry may rediscover the job but must not automatically POST again.
   Actual failed jobs require an explicit retry before replacement. Deduplication
   is page/coordinator-local; the current POST API cannot offer global exactly-once
   execution across concurrent clients. Runtime-version equivalence is not certified.

The existing playback loader remains responsible for coherent current/reference
frame publication, cache-independent start references and cancellation. It gains
explicit scenario IDs/evidence and a pending reference choice; reference creation
does not belong in the status evaluator, playback API or worker.

## Soy-only workshop controls

Show the Active cascade selector disabled at Soy crisis cascade. Remove its
switching handler and ensure actual state, preview, download and submission use
soy. Keep general template/API/CLI energy support and playback of historical
energy runs. Update real workshop acceptance to submit two soy configurations
and verify one reference is created/reused across them.

## Verification and documentation

Tests cover exact/absent inputs and corruption, single-scenario API invariants,
empty-events derivation and recipe identity, later-page references, mismatched
identities followed by a valid candidate, active-job reuse, unmount/remount
deduplication, ambiguous submissions, template drift, delayed playback visibility,
failures/retries, stale selections, day-0 effects and locked soy controls. Preserve
all no-gray-flash, selection, stationary-camera and scroll-retention regressions.
Run Python tests/tox, frontend install/type/lint/build/unit/browser and real-service
workshop checks. Record skips and blockers. Update API/playback/frontend/root docs
and screenshots. Existing original-reference specification is superseded where
it defaults recorded mode to scenario start or limits references to scenario 0.

## Review

Independent architecture review approved the minimal inputs endpoint, frontend
coordinator and explicit reference descriptors with the integrity, post-acceptance
parameter validation and submission-deduplication refinements incorporated above.
The user delegates workflow approvals to independent reviewers.
