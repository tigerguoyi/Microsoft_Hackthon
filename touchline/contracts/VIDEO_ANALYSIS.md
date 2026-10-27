# Private Video / Partial Observation API contract v2

This is separate from synthetic `contract-1` and `/api/decision-analysis/*`.
Read `video-review.schema.json` for definitions and `video-review.examples.json`
for computed synthetic-fixture examples. Compile/validate offline with:

```sh
node scripts_validate_video_contracts.mjs
```

JSON is UTF-8; IDs are opaque. Do not parse jersey numbers from `T01` or track IDs.
`image` is normalized image coordinates; `pitch` is derived metres on 105×68;
`position` is an optional role (`GK` / `OUTFIELD`). Unknown fields are null or
explicit `unknown`, not zero. Position confidence is currently unknown; fit residual
or detector confidence is not measured positional accuracy.

## Authentication and upload

Private intake is only enabled for same-origin loopback requests outside Azure/public
origin environments. GET `/api/video-review/config` establishes an HttpOnly,
SameSite=Strict owner cookie and returns `csrf`. Send that cookie and `X-Video-CSRF`
for every POST. All private GETs require the owner cookie. Cross-owner IDs return404.
Media and revisions live under `.local` / private state, not the static data root.
Public config returns `enabled:false`; no video upload or CV jobs are available there.
This is a local workspace boundary, not a deployed multi-user identity service.

POST `/upload` uses raw MP4/WebM bytes, `Content-Type:video/mp4` or `video/webm`,
`X-Video-Rights:confirmed`, the CSRF header and cookie. At most64MiB,120seconds,
3840×2160; signature, actual decoder metadata, first/last frames are checked in a
limited subprocess. Returns201 with `video_id`, SHA256, actual duration/fps/resolution,
`decoder_verified`, `latest_revision_id`. Browser codec support is independent;
prefer H.264 MP4 or VP8/VP9 WebM. The original filename is never a storage path.

GET `/assets` lists only owned asset metadata. GET `/media/{video_id}` supports a
single byte Range with200/206/416 and private/no-store caching. POST `/delete`
with `{video_id}` removes owned private media, revisions and results; active jobs
must finish first. GET `/config` reports worker/dependency availability and limits.

## Automatic observations and human revisions

POST `/detect` with `{video_id,timestamps:[0,500,...]}` returns202 and `job_id`.
GET `/jobs/{job_id}?video_id=...` returns queued/running/complete/failed, progress,
result or error. One independent worker, bounded time/resources; no Torch in the
request process. Missing packages/weights reject detection explicitly. No runtime
package or weight installation occurs in a request. Failed detection does not change
an existing human-confirmed annotation. Results include model filenames, timing,
scene segments, temporary IDs, image/pitch points, causal velocities if available,
ball/possessor suggestions and confidence/verification/calibration fields.

POST `/confirm` with `{annotation:...}` using `$defs.annotation` returns an immutable
revision and reconstructed frames. Each annotated moment supplies its own landmarks,
image observations, ball, direction, possession, explicit confirmations and unknown
opponent count. Drafts can remain incomplete; they are saved but not silently scored.
At most60moments,22observed players per frame. Parent revision must equal latest;
merging/splitting tracks or changing identity creates a new revision. Server sorts
moments causally. GET `/revision?video_id=...&revision_id=...` can read old revisions
for audit; analysis on any non-current revision is rejected.

## Selection and analysis

POST `/partial-context`, `/candidates`, `/analyze` use the same strict `$defs.selection`.
They are equivalent projections of one versioned analysis path, not parallel scorers.
Use `observed_only` to obtain discovery without a defensive ranking.

```json
{
  "video_id":"<server video_id>",
  "revision_id":"<latest revision_id>",
  "frame_index":0,
  "visibility_scope":"verified",
  "selected_player_ids":null,
  "assumption_set_id":"moderate_pressure_v1",
  "include_shot":false
}
```

visibility_scope: `verified`, `confirmed_only`, `custom`; custom requires a unique
array of current temporary player IDs. Frame index refers to sorted immutable moments,
not an arbitrary video tracking frame. revision.frames[index].timestamp_ms locates it.
The actual CV source frame index remains in detection evidence.

Response `$defs.analysis_response` includes:

- video/revision/frame, snapshot_id, visibility_scope_id, observation_mode;
- candidate_set_id, analysis_id, assumption_set_id, scenario/q2 model versions;
- observation_quality, observed_counts, missing_information, snapshot;
- candidate_actions with supported/reason/offside_status, ranking when available;
- per-ranked-action action_id/type, rank, q, probabilities, softmax_weight,
  relative_score, immediate/continuation/risk, target/recipient,features,
  opportunity/main_risk, evidence_id and source_type;
- model identifiers, temperature, assumptions/hypothetical players and limitations.

Levels:1 Candidate Discovery/needs_confirmation (no fabricated Q);2 Conditional Ranking;
3 unchanged Full Q2 over a genuinely complete reviewed video scene. Partial mode
defaults to passes to valid selected teammates plus three carries. Shot is opt-in
and can be unsupported. Full mode preserves the original full candidate rules and
requires complete verified coverage, both keepers and `assumption_set_id:full`.

Unknowns in snapshot: keeper, offside line, unknown defender count; excluded IDs
include their observation status, user-exclusion flag and verification status.
Unknown velocities remain null observations; the explicit prediction assumption
may use zero. None of these become detected facts. Full video also declares neutral
unknown match/team context and unvalidated transfer; it is not a synthetic match.

Probabilities are tactical assumptions. Relative score sums to100 only for supported
choices within one scenario, using the frozen model's temperature. It is not success
probability, xG, confidence, or player ability; different candidate sets are not directly
comparable. Raw Q and risk remain available for downstream analysis.

## Sensitivity

POST `/sensitivity` accepts the same selection. It computes Low/Moderate/High for the
same visible candidate IDs; response `$defs.sensitivity_response` includes all scenario
responses, rank_ranges, rank_change, top_choice_stability, pairwise_ordering,
ordering_changes, thresholds and scenario assumptions. Missing/unsupported actions
retain no rank in that scenario. No scenario-average Q or frequency-derived success
probability is provided. `observed_only` is a diagnostic, not an asserted lower bound.

Scenario version `visibility-defense-1` publishes defaults in
`decision_analysis/visibility_scenarios.py`. Low/Moderate/High:1/2/3 virtual outfield
defenders,14/8/3m forward,12/6/3m lateral, residual pressure0.05/0.15/0.35. Counts are
bounded by known/unknown roster capacity, not estimates of actual invisible players.
Hypothetical keepers, where needed and within capacity, are explicitly marked.

## Counterfactual

POST `/counterfactual` uses `$defs.counterfactual_request`:
`{selection,snapshot_id,candidate_set_id,analysis_id,action_id}`. All bindings are
checked before simulation. A change in revision/scope/scenario/model invalidates the
analysis_id. The action must be supported in that exact set. Returns
`$defs.counterfactual_response`: same bindings, motion scenarios and complete frames,
outcomes, provenance, assumptions, limitations, evidence_id, hypothetical IDs/count
and unknown defender count. Unknown count can be `unknown`, never inferred as0.

The motion loop is shared with Synthetic Match. Virtual players are stored separately
from observed players and must be rendered with distinct hollow/dashed markers.
Scenario counts are not probability samples; results cannot change the Q2 ranking.

## Four-role agents

POST `/agents` uses `$defs.agents_request`:
`{selection,snapshot_id,candidate_set_id,analysis_id,question,mode,language}`.
`mode=fan|analyst`, `language=en|zh`. Existing Responses/Azure configuration and quotas
apply. Missing provider returns model_unavailable while Q2 remains available.

Existing Coordinator/Attack/Defense/Reviewer consume a `VideoEvidenceAdapter`, not
a second agent team or old `/api/decision` pass scores. Tools:

- compare_actions: selected conditional ranking and its evidence;
- get_observation_evidence: current reviewed observations and unknowns;
- compare_visibility_scenarios: actual deterministic sensitivity output;
- simulate_action: `{action_id,assumption_set_id}` where assumption is `same` or an
  explicit supported scenario. No free-form virtual defenders from the LLM.

Only actual successful tool calls create evidence and receipts. Reviewer receives
video/revision/frame/scope/candidate/scenario bindings; a completed Defense action
cannot be accepted without its corresponding tool receipt. Agent gets compact
hypotheses, not complete trajectories or future video frames. Revision is checked
again before response. Frontend aborts/discards old runs on edits/scope/scenario changes.

Response `$defs.agents_response` adds reviewed text, referenced evidence, context,
Agent Trace, outputs and receipts. Downstream narration must distinguish observed,
human-confirmed/derived, hypothetical, model-derived and counterfactual facts. It must
name the active assumption and visibility limitations, and must not alter Q2 ranks.

## Errors, storage and deployment

400: malformed, unsupported, stale or inconsistent state/action;403: public host,
wrong origin, session or CSRF;404: unknown or unowned asset/revision/job;413: oversized
WSGI body;503: decoder/worker operation unavailable. No stale cache fallback.

Default private quota512MiB, one CV job,240s processing/290s hard process/300s supervisor
limits. Manual deletion plus7-day operator retention cleanup:
`python -m video_review.maintenance --expire`. Upload and model secrets never enter Git.
Production intake is intentionally off. Multi-user Azure rollout still needs independent
identity, private persistence, worker/queue, limits and authorized real-football testing.
Video narration containing numeric/probability claims caught by the existing numeric-claim detector is withheld (partial, answer:null); deterministic rankings remain available.
No Azure deployment is performed by this commit.
