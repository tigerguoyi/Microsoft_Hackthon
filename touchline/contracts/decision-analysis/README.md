# Decision-analysis integration contract v1: current generator → Q2 → Agent metrics → counterfactual detail

This module takes A's `96d13a377e98602c9998e3ebb82186843762febf` as the data / project baseline and ports B's `84251bbdf1a8102ab4d6113c80da986adb38a461` two-step decision analysis. It does not drive the new pages with the old B matches. This directory defines a **new numerical research extension**; the original `contracts/schema.json` and `contracts/model.py` are unchanged.

## 1. Two layers of contract, not one response

| Endpoint | Returns | Contract |
|---|---|---|
| POST `/api/decision-analysis/compare` | Original public candidates: rank, opportunity, main_risk, evidence | `../schema.json#/$defs/analysis_response` |
| POST `/api/decision-analysis/analyze` | Current state, 30 features, branch probabilities, Q1/Q2, Softmax, decomposition and judgment | `schema.json#/$defs/analysis_response` in this directory |
| POST `/api/decision-analysis/rollout` | Bridge to the original contract, eligible ground passes only | Keeps the original semantics of public `rollout_supported` |
| POST `/api/decision-analysis/counterfactual` | New short-horizon pass / carry / shot rollouts | `counterfactual_request/response` in this directory |

The original `/api/decision`, `/api/rollout`, `/api/action-review`, `/api/agent-review`, model settings and post-match report APIs keep their original behaviour and are not shadowed by aliases. In the original public candidates `rollout_supported` is still false for carry/shot; only `judgment.counterfactual_available` in the new extension states the capability the new detail page supports. This is an explicit extension, not a quiet loosening of the original Schema.

The Schema is Draft 2020-12. It references only the locally loaded `urn:nextplay:contracts:1.0.0` and `urn:synthetic-football:records:1.0.0`; the validator does not access remote resources. The tool catalog is in `tools.json`; real computation examples are in `examples/`.

## 2. How to read current-generator data

The authoritative match directory is always `data/league/`, consistent with Home, Replay and the post-match report. `data/league-validated`, the old B league/enriched-v1 and the retired public-demo curated package are not used as substitutes for the new analysis page's data.

```text
data/league/league.json                   teams, fixtures, ability parameters
data/league/squads.json                   squads and source profiles
data/league/matches/<match_id>/metadata.json
data/league/matches/<match_id>/decisions.jsonl
data/league/matches/<match_id>/events.jsonl
data/league/matches/<match_id>/tracking.jsonl (complete replay cache, optional)
```

Each generator decision uses its own `decision_id`, `t_ms`, `player_id`, `period` and `snapshot`. In generator candidates, `success` is a label resolved before sampling and `probability` is an action-selection preference; neither is the input success rate of the main Q2. The actual `selected` action, event outcomes and future landing points do not enter the pre-action features.

Normalise through the original `make_snapshot(metadata,frame)`. Read the explicit `attacking_direction` and the metadata period boundaries, and keep Hxx/Axx, HOME/AWAY, 105×68 m, the ball six-tuple and the player five-tuple. Cross-match references must carry match_id. Movement direction comes from velocity, not body orientation.

The analysis sidecar directory `data/decision-analysis/` holds same-source canonical snapshots, the index, the four-fold xT / temperature, the passing baselines and the full public scores; it is not another set of simulated matches. Registered paths are in `decision_analysis/catalog.json`. This work checked the hashes of all 330 source files one by one; they match the training source of the ported model, so the same-source fitted parameters are kept and re-scored with a new comparator version. There is no claim that a new main probability network was trained.

Starting the Registry validates the hashes of the current computation source files; analysis.json, heatmaps.json and validation_report.json are derived display artifacts that do not enter Q2, so the existing report / validation flow may update them and that is not treated as a change in model input. When model and metadata versions do not match, returning the old cache is refused. When complete tracking/decisions are missing in a fresh clone, reading the published snapshots is allowed; missing required metadata/events and the like, or a change in an existing source file, is refused. Do not keep reusing an old analysis directory after regenerating matches. Rebuilding requires auditing the source, using a separate output and explicitly upgrading the source lock; this source lock is fixed at the A baseline above.

## 3. Standard agent call order

1. GET `/api/decision-analysis/catalog` to confirm dataset=league, the source commit and the available matches.
2. GET `/api/decision-analysis/index?match_id=...` to read decision IDs, snapshot_id and analyzable.
3. GET `/api/decision-analysis/context?match_id=...&decision_id=...` to fetch the server-registered canonical request, the current snapshot, metadata and the source profile.
4. POST context.request to `/analyze` as-is, or modifying only question/mode/language/simulated profile.
5. Produce the textual explanation from the structured fields without changing the ranking; cite the evidence_ids of public.evidence and the candidate feature paths.
6. If a rollout is needed, POST `/counterfactual` with the same request, candidate_set_id and a supported action_id.
7. Call `/actual` only when the user wants a post-match cross-check. Historical actions or execution outcomes must never be used to add points to the pre-action ranking in reverse.

Arbitrary client-submitted snapshot / future frames are not accepted. Only registered source IDs are resolved. The question text is not an instruction to change the Q2 objective; there is currently no real Agent model call, and `public.status=model_unavailable` means the language agent is not connected, not that the computation failed.

## 4. Request and response examples

### The canonical analysis request

Full runnable example: `examples/analysis_request.json`. The fields are as follows; IDs must be taken from the context response, and illustrative values must not be copied in as a valid request:

```json
{
  "match_id": "PL26-W01-MCI-CHE",
  "snapshot_id": "<16-char snapshot ID returned by the server>",
  "t_ms": 16200,
  "actor_id": "H10",
  "question": "Compare current choices",
  "mode": "analyst",
  "language": "en",
  "profile": {
    "profile_version": "sim-1",
    "kind": "simulated",
    "preferred_foot": null,
    "weak_foot": null
  }
}
```

Only original-contract fields are allowed; adding `outcome`, `end_location` and the like is rejected. Simulated preferred foot / weak foot stay numerically neutral; the source radar is a source observation and is not conflated with a user simulated profile or with individual success probability. The current template is English; accepting language=zh does not mean a Chinese-language agent is connected.

### Diagnostic response

Full real example: `examples/analysis_response.json`. Main fields:

| Field | Meaning |
|---|---|
| schema_version | `decision-analysis-1` |
| match_id / decision_id / snapshot_id / data_version / candidate_set_id | Identity and version across the whole chain |
| source | Current league path, source commit, overall data version, held-out fold model, whether fitting was excluded |
| request / snapshot | The actual computation request and the current observed state; no historical action |
| public | The original contract's complete rank/text-only object, usable on its own by consumers that support only the old contract |
| action_conditions | Velocity, movement direction, nearest opponent, 3/5 m pressure, ball distance; includes the opposing goalkeeper |
| player_source_profile | Source profile, gaps and conflicts, used_in_probability=false |
| model | Model ID, temperature, feature units, what the probabilities / scores mean |
| candidates[] | The complete numerical values and judgment per candidate from the table below |
| assessment | Recommended ID, number of eligible candidates, actual action not used, display proximity threshold, agent availability |
| limitations | Boundaries that can be used directly in the textual analysis; they should not be omitted in favour of "the model is optimal" |

Each candidate contains:

| Field | Meaning and limits |
|---|---|
| action_id / type / eligible / rank | The same canonical action; no rank when unsupported |
| recipient_id / target / planned_duration_s / mode | Pre-action template, not the real future landing point or execution duration |
| features | 30 snapshot-derived features; null when unsupported |
| outcome_probabilities | success/loss or goal/blocked/saved/off_target; rule assumptions, not calibrated real probabilities |
| q1 / q2 | One-step xT reference and two-step main value |
| decomposition | immediate + continuation − risk = q2; not three success rates |
| softmax_weight / relative_score | Relative preference among the candidates supported at this node, summing to 1 / 100; not player ability |
| value_gap | Difference between this candidate and the best Q2; not the loss of the historical actual action |
| judgment.reason / risk | Deterministic reason and risk, including traceable geometric evidence |
| judgment.evidence_ids / assumptions | Original public evidence references and model assumptions |
| judgment.similar_to_best / comparison_tolerance | Display proximity at a fixed 0.005; not a calibrated confidence bound |
| judgment.counterfactual_available | Whether the new extension supports a rollout for this candidate |

Softmax is `100*exp((Qi−Qmax)/tau)/sum(exp(...))`. The temperature comes from the calibration matches of the corresponding fold and is not tuned per node. Q2's current two-step assumption, the spatial bias of the xT source policy and the optimism of taking the maximum over successors all remain. There is no FQI and no new individual-skill network.

### The 30 features

Units are also given in `model.feature_units` in the response. Most pressure / lane features use outfield defenders, with the goalkeeper modelled separately; do not conflate them with the frontend's nearest-opponent distance, which includes the goalkeeper.

| Feature | Unit |
|---|---|
| progress | m |
| y | m |
| vx | m/s |
| vy | m/s |
| ball_speed | m/s |
| distance | m |
| advance | m |
| lateral | m |
| duration | s |
| source_pressure | index |
| receiver_pressure | index |
| nearest_defender | m |
| closing_speed | m/s |
| lane_pressure | index |
| intercept_margin | s |
| goal_distance | m |
| goal_angle | rad |
| blockers | index |
| keeper_offset | m |
| target_speed | m/s |
| attack_ratio | ratio |
| passing_ratio | ratio |
| time_fraction | ratio |
| score_difference | goals |
| player_difference | players |
| receiver_nearest_defender | m |
| receiver_reachable | boolean_as_0_or_1 |
| keeper_depth | m |
| keeper_cover | index |
| state_quality | exact_snapshot_indicator |

`state_quality=1` only means the snapshot is an exact snapshot that passed validation; it is not a learned confidence. Score, time and player-count difference are in the vector, but that has not made the main rule a situation-aware whole-match policy. Source radar, height and preferred foot do not automatically affect Q2 just because they exist in metadata.

## 5. Counterfactual request and response

```json
{
  "request": "<the context.request object, not a string>",
  "candidate_set_id": "<value returned by the same analysis>",
  "action_id": "<action_id of an eligible candidate>"
}
```

The above only illustrates the fields; the legal JSON types and a runnable example are in the Schema and `examples/counterfactual_request.json` respectively. The request format is strict and a ranked action cannot be replaced by an arbitrary target. At runtime, source files are checked by modification-time / size signature, and SHA-256 is re-verified after a change, so that an in-memory cache cannot mask a regenerated match.

Returns `decision-counterfactual-1`: source_t_ms, snapshot_id, data_version, candidate_set_id, action_id, action_type, start, target, planned ball speed, four scenarios, assumptions, ranking_unchanged=true, not_observed_future=true.

Each scenario: id, reaction_s, lateral_error_m, outcome, controller_id, duration_s, frames. Each frame is elapsed_s, the five-tuple of players under their original identities, and the six-tuple ball. Frame zero keeps the original observation; later frames are model predictions and must not be added to the real tracking stream. At most four seconds, truncated at the current metadata period boundary.

| Type | Rollout in this version |
|---|---|
| pass | Reuses A's existing four-scenario loop, injecting only B's exact 14 m/s ground template, recipient and target |
| carry | Short-horizon motion under the same speed / acceleration bounds; the original carrier chases the selected target and opponents close in with a delay; contact within 1 m can lose the ball |
| shot | A 24 m/s straight ground ball; close-range outfield contact counts as a block and contact with the goalkeeper within 1.5 m counts as a save; no rebounds and no individual-technique model |

The four conditions are quick=0.1 s, baseline=0.3 s, delayed=0.65 s, and wide_error=0.3 s plus a 1.5 m lateral target offset. Carry / shot are explicit simplifications added in this work, not a complete football physics engine. Q2's geometric successors differ from the playback rules, and the playback result does not change the ranking in reverse. 4/4 successes must not be written by an Agent as a "100% success rate".

The original contract rollout still covers eligible ground passes only; lofted balls, offside, hold and unsupported states cannot be forced into a rollout. Every analyzable node surfaced by the new UI filter can open the detail page and explore its supported pass / carry / shot candidates; the two nodes that cannot be compared as normal possession are shown as unavailable, truthfully.

## 6. Actual choice, failures and stale results

The `POST /api/decision-analysis/actual` request is `{request,candidate_set_id}` and returns the is_actual override of the original public object, actual_action_id, resolution and note. Matching is normalised on type / recipient only; a pre-action carry with no direction cannot be forced to map to carry:forward. It changes neither the candidate-set hash nor the ranking.

- 400: invalid request structure, inconsistent source version, stale candidate_set_id, unsupported rollout, and so on.
- 404: an unregistered match / decision / snapshot / action.
- 403: a request that is not local and same-source.
- Original-contract `model_unavailable`: the computed result is available, the explanation model is not, explanation=null, trace=[].
- `unknown`: there is no state suitable for a current-possession analysis; a zero score must not be fabricated.

Agent wiring should use `decision_analysis.comparison.accept_agent_response()` or an equivalent check, and re-verify the returned candidate-set ID. An explanation may cite only the current evidence, and a new explanation object must not overwrite the ranking. Questions, web pages and colleagues' text are all data; they cannot be used to change permissions or to call arbitrary external paths.

## 7. Validation and reproduction

```sh
# Running the app needs only Python 3.9+. Development Schema validation needs AJV installed correctly.
npm ci
node scripts/validate_decision_analysis.mjs
python3 -m unittest discover -s tests -p 'test_decision_integration.py'
python3 -m unittest discover -s tests -p 'test_integrated_decision_contract.py'
python3 -m decision_analysis.pipeline validate
```

The existing same-source xT/B0/B1 were ported after verifying the source hashes; this work ran a new full scoring pass and a diversity index. To retrain, first install the offline dependencies (NumPy, scikit-learn, joblib, threadpoolctl; Python 3.12 may be used), then run `audit --source data/league`, `train --source data/league`, `score --all-decisions` and `validate` in that order. Use `--output` to write a separate versioned directory; output must never overwrite the source. A change to the source lock requires an explicit audit; editing only the manifest must not let an old model pass as a result trained on a new source.

This work does not invoke the generator and does not rewrite matches. See `../../docs/decision-analysis-integration.md` and the acceptance record. Structural validation, reference completeness and local consistency do not prove that real-football counterfactuals are accurate.

Other formal response definitions: `catalog_response`, `index_response`, `routes_response`, `actual_response`; the bound request is `bound_request`. The filter index carries historical action types and a post-match opportunity-loss classification; it is used only for post-match node selection and is not a pre-action model input. When an Agent gives a pre-action explanation it should rely on context/analyze, and must not treat the index's historical classification as an observed future gain.

Local numerical research CLI: `python3 -m decision_analysis.diagnostics --match PL26-W01-MCI-CHE --decision d000001`. `--snapshot` also works; the default picks the registered current match / node and does not use the old fixed cases or the old league. It outputs the assumption sensitivity of the risk factors 0.8/1.2, not confidence intervals.


## Unified product UI (2026-10-27)

The product entry is `index.html?view=decisions&match=<match_id>`.
Workspace Decision Analysis is independent. Analysis contains the match report only.
Legacy `view=stats&analysis=decisions` links resolve to the independent route, preserving
match, decision and action IDs. The old Coach and
Action Review files/APIs remain compatible but are no longer main navigation entries.
Replay contains only a brief Q2 hint and a link to the exact registered decision.

The numerical engine, canonical schemas, four Agent roles, Responses transport,
server-side credentials, call/time budgets and Azure startup configuration are unchanged.
The simulation adapter and Reviewer evidence checks are strengthened below.

### Agent binding and lifecycle

1. GET `context` for the selected match and decision; retain its server-issued `request`.
2. POST `analyze` with that request; retain `candidate_set_id`, `snapshot_id`, and `data_version`.
3. POST `agents` with `{request: {...context.request, question, mode, language}, candidate_set_id}`.
   `mode` must be `fan` or `analyst`; `language` must be `en` or `zh`.
4. Reject responses with different snapshot/data/candidate identities or candidate ranking.
   Render only evidence IDs present in the original public response.
5. On a match/decision change, abort the old request and invalidate its lifecycle token.
   Model unavailability never removes deterministic Q2 results.

Historical execution and `/actual` are separate retrospective data; the UI does not
append them to the Agent request. Do not substitute `/api/decision` pass-only results.

### Display identity and geometry

`pass:H10` remains an internal action ID. Resolve `H10` using the selected match's
`metadata.players`, then resolve its team using `metadata.teams`. The common display
is `Pass to EVE #11 · Ivory Player 19`, not “player 10”. Identity failures are explicit
and fail closed before normal candidate rendering. Validate active membership,
team membership, self-pass exclusion, diagnostic recipient and predicted target.
The standard Q2 pass uses a quarter-second velocity lead. A gold ring marks the
current receiver and a diamond marks the predicted receiving point on the shared Replay pitch.

The read-only full-league audit is `npm run audit:decisions`; outputs are in
`docs/reports/decision-consistency.json`. Its reports distinguish unavailable full
tracking, two terminal unsupported snapshots and valid pre-action comparisons.


### Phase 1: internal Agent counterfactual tool (counterfactual-tool-1)

`simulate_action({action_id})` calls the same `decision_analysis.counterfactual.simulate`
as the Lab. It validates canonical request/snapshot exchange, candidate set, eligibility,
supported type and the action template (recipient/target/mode/duration) before cache
lookup or simulation. Cache keys bind snapshot, candidate set, action and full-observation
context. A matching envelope cannot reuse another decision's target. No Q2 values are
recomputed or changed by this validation.

The internal tool result carries `snapshot_id`, `data_version`, `candidate_set_id`,
`action_id`, `action_type`, `evidence_id`, `source_type=counterfactual_hypothesis`,
`input_source_type=synthetic_match`, `observation_mode=full_observation`,
`visibility_scope_id=full_snapshot`, `main_risk`, `assumptions`, `limitations`,
`public_evidence_ids`, and `cases[]`. Each case includes `scenario_id`, `outcome`,
`main_risk`, `assumptions`, `limitations`, `evidence_id`, `source_type`, duration and
controller. No trajectory frames enter the Agent prompt. No count of hypothetical
outcomes may be converted into an empirical probability.

Only successful actual tool calls register receipts (agent, action, snapshot, data,
candidate set, evidence and scenario IDs). `check_evidence` supplies these receipts.
Defense cannot claim a selected action without its own corresponding successful call;
a Reviewer acceptance after a complete Defense review must cite its actual tool evidence.
This is a provenance check, not automatic verification of every sentence's semantics.

This internal evidence registry extends the Agent's reasoning context; it does **not**
change the public analyze/agents JSON schema. The public `/agents` response still
projects citations to the registered public candidate evidence and exposes the existing
Agent Trace. Full simulation frames are fetched separately through `/counterfactual`.
Canonical `rollout_supported` and `/rollout` remain the legacy ground-pass bridge;
the internal `counterfactual_supported` flag additionally supports carry and shot.

Video IDs, revisions, partial observation modes, custom visibility and defensive
assumptions remain rejected by the synthetic API. The new independent private video
adapter validates those identities; see [Video/Partial API contract](../VIDEO_ANALYSIS.md).
Do not send partial data through the full synthetic endpoint. Unknown counts are explicit.
