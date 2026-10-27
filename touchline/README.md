# Touchline — NextPlay League 2026/27 replay and squad explorer

A dependency-free football data demo for match replay, event consumption, live statistics and squad browsing. Club names, grounds, squad numbers and player details are fictional. Every match result, event and tracking frame is procedurally generated. Provenance for the imported upstream tree is in `SOURCE.md`.

## Checked-in sample and how to regenerate

This checkout contains all **40 match directories** and **91,031 decision snapshots**.
Full `tracking.jsonl` files are not checked in: animation uses the 60-second previews,
while Decision Analysis reads the separate registered full-match decision snapshots.
Do not regenerate matches to enable the new navigation or Agent tools. The following
commands describe the existing generator for separate research outputs; they are not
part of this Phase 1–3 change and can overwrite data if run against the checked-in path.

From this directory:

```sh
# League index for 4 matchweeks, no full-tracking files, keep two sample matches
python3 generate.py --weeks 4 --tracking none --retain-matches 2

# Legacy single match used by core tests (also writes gitignored data/tracking.jsonl)
python3 generate.py --mode single --output data

# Full local league. Featured tracking is the default and is roughly 300 MB.
python3 generate.py --weeks 4 --tracking featured

# Alternate seed, written outside the sample tree
python3 generate.py --seed 12345 --output data/league-alt
```

`--retain-matches` still simulates every fixture so `league.json`, `fixtures.jsonl` and `standings.json` stay complete, then deletes match directories that are not kept. `validate_league.py` expects every match directory on disk and passes only after a generate run **without** `--retain-matches`. `npm test` checks the current full decision dataset and the existing sample contracts.

`python3 validate.py` on the legacy match needs `data/tracking.jsonl`. Generate single mode first. `package.py` also reads that tracking file and writes `football-simulation.zip` next to this directory.

## Frontend

The Touchline dashboard reads `data/league/` directly. No build step, CDN or third-party package is required.

```sh
# From the project root (Python 3)
python3 server.py

# Or use the npm shortcut
npm run dev
```

Open <http://127.0.0.1:5173>. Serve the folder over HTTP rather than opening `index.html` directly: the browser needs to load JSONL files and a module Worker.

A hosted instance runs the same code on Azure App Service. `wsgi.py` exposes the
same handler through WSGI and `startup.sh` starts it under gunicorn; `deploy/`
holds the steps that publish it. The instance's own hostname has to be listed
in `ITG_ALLOWED_HOSTS`, because the server only answers requests it considers
same-origin.

### Language

English is the default in every view: the dashboard, the coach page, the action
review page, the validation page and the counterfactual page. The
source text is English, so a page reads correctly even before scripts run.

The coach page keeps a `语言 / Language` selector. Choosing Chinese swaps the
display strings through `coach-i18n.js`; identifiers, scores and exported evidence
are never translated, and switching language discards in-flight model prose rather
than mixing the two. The choice is remembered in `localStorage`.

The only Chinese left in the source is the selector's own `中文` label, the Chinese
default question that `coach.js` applies when the language is `zh`, and the
dictionary in `coach-i18n.js`.

### Views

The default landing page is **Home**. Choose any of the 20 clubs and click
**Set home club**; the browser remembers this choice. The simulation clock defaults
to **the start of matchweek 3 (7 November 2026)**, independently of the computer's
clock. Home shows form, results, goals, points and league position using only weeks
1–2; week 3 is the next fixture and week 4 is on the horizon. Future scores never
enter these homepage calculations. Click a past result to open its match report.
The match explorer defaults to week 3 (your club's match when selected); explicit
`?match=` links still open the requested replay. The explorer remains an archive
of all generated matches. `CURRENT_MATCHWEEK` in `club-home.js` sets the clock.

- **Select match** — filter 40 fixtures by matchweek, or use previous/next. `?match=<match_id>` deep-links a match.
- **Overview** — score, possession, shots, passing, interceptions, pressure events, event feed and player focus.
- **Replay** — smooth 5 Hz tracking for players and the ball, 1× / 4× / 10× speed, timeline scrubbing and ±10 second controls. Red cards remove players; substitutions switch to the incoming player's identity. Space toggles playback; arrow keys jump 10 seconds.
- **Analysis** — an English post-match report, first- and second-half review, match progression, Player of the Match with evidence and leading performers, plus final match statistics.
- **Decision Analysis** (Workspace, `?view=decisions`) — decision timeline, filters, player action conditions, ranked Pass / Carry / Shot choices, Opportunity / Main Risk, Counterfactual, Ask AI Coach, Evidence and Agent Trace. Analysis contains reports only. Old `?view=stats&analysis=decisions` links still work.
- **Video Analysis** — private local video upload, optional CV preannotations, human revisions, conditional Partial Q2 and visibility sensitivity, Counterfactual and the existing four-role AI coach. Public/Azure intake is disabled; authorized real-football positive validation remains outstanding. See [setup, evidence and limitations](../HANDOFF_VideoAnalysis_PartialQ2_20261027.md).
- **Real-data validation** — existing independent validation tools remain available.
- **Lineups** — matchday XI plus substitutes, appearance status, cards and simulated distance.
- **Squads** — a new league-wide tab with all 20 clubs' 2026/27 rosters. Pick a club, search by player, position or nationality, and browse players grouped by goalkeepers, defenders, midfielders and forwards.

The replay starts at the selected match's `preview-60s.json` clip. Matches marked `tracking: "full"` continue loading the complete `tracking.jsonl` in a Web Worker; all other matches remain a 60-second preview. If full tracking fails, the preview stays usable. Selecting a match reloads its `metadata`, `summary`, `events`, `states` and `preview` files.

### Independent match-summary model service

Run `npm run dev` (or `python3 server.py`) and open **Settings**. Enter an HTTPS
Responses API base URL, model ID and API key, then save. The service must support
structured JSON output. In **Analysis**, click **Generate model summary** to write
and save a new full-match and half-by-half review for the selected completed match.
The request sends the computed match report to your configured provider and may
incur provider usage charges. Scores, statistics, evidence and Player of the Match
remain computed locally. Failed requests leave the existing report intact.

#### Pointing it at Azure AI Foundry

The deployment can come from the environment instead of the Settings page, so a
server can run without anyone entering a key:

```sh
export ITG_MODEL_BASE_URL="https://<resource>.cognitiveservices.azure.com/openai/v1"
export ITG_MODEL_NAME="gpt-4.1-mini"
export ITG_MODEL_API_KEY="<key>"
python3 server.py
```

The Settings page overrides these for a local session. The key stays on the
server: only whether one is configured is exposed to the browser.

Azure AI Foundry authenticates with the `api-key` header and OpenAI with a bearer
token. `model_service.auth_headers` sends both, so one client reaches either
deployment and the base URL is the only difference.

`ITG_DAILY_CALL_CAP` (default 200) bounds how many model calls a day the server
will make. When the cap is spent, `/api/agent-review` returns `model_unavailable`
with the computed comparison still attached, and the match-summary route returns
502 without touching the stored report. A public demo entry cannot run up a bill.

`model_service.py` owns model narration independently of `analysis_agent.py`.
`server.py` provides same-origin settings and generation APIs on loopback only.
The key is saved in `.local/model-service.json` with owner-only file permissions;
this directory is ignored by Git and blocked from static serving. Settings responses
only expose whether a key exists. Leave the key blank to retain it, or choose
**Remove saved API key**. Changing the service URL requires entering a key again.
Do not serve this directory with a generic static server after saving credentials.
Pure static hosting can still show pre-generated reports but cannot use settings
or generate new model summaries. This server is intended for local personal use.

### The agent team

Four roles reason over one frozen snapshot, in a fixed order:

| Role | Job | Tool |
| --- | --- | --- |
| `coordinator` | Understand the question, delegate in order, synthesise | `delegate` |
| `attack` | Compare the options and their trade-offs | `compare_actions` |
| `defense` | Attack the conclusion: interception, sensitivity | `simulate_action` |
| `reviewer` | Check citations, assumptions, overreach; accept or reject | `check_evidence` |

The candidate set is the full comparison, not only passes: passes, three carries,
a shot when in range, and holding. The roles share one evidence registry, so a
number in the answer traces back to a computed value. Agent `simulate_action` now
uses `decision_analysis.counterfactual.simulate` for supported Pass / Carry / Shot,
returning compact summaries and actual tool receipts; complete frames remain in the Lab.
Hold and unsupported or stale candidates are rejected. Reviewer verifies completed
Defense simulations against the receipts. Four deterministic scenarios are hypotheses,
not success-probability samples. The old public `/api/rollout` and canonical
`rollout_supported` flag keep their ground-pass-only compatibility semantics.

Public Demo and its dedicated static scorer/build script are removed. `/public-demo`
and descendants return HTTP 410 through both the local handler and WSGI. Shared
models and data are retained. The synthetic API still rejects video/partial contexts. The independent `/api/video-review`
adapter now handles versioned partial states; missing defenders are not interpreted as zero.

See [Phase 1–3 handoff](../HANDOFF_Phase1-3_20261027.md).

If the audit rejects the answer, the coordinator rewrites it once. If the rewrite
does not hold up, only the computed comparison is returned. Every specialist
recovers on its own: a failure is reported as the missing review rather than
silently replaced with rule-based prose.

#### The analysis contract

The contract itself is the `contracts/` package: `schema.json` is the published
shape, `model.py` holds the hashes and the cross-field checks, and
`export_fixtures.py` pins the three fixed cases under `tests/fixtures/contracts/`.

`decision_analysis/service.py` connects it to the running system, and
`POST /api/decision-analysis/analyze` is the route the interface and the agent
share:

```json
{"match_id": "SYN-SINGLE-0001", "snapshot_id": "f181321fea364728",
 "t_ms": 15600, "actor_id": "H10", "question": "Why not pass to #9?",
 "mode": "fan", "language": "en",
 "profile": {"profile_version": "sim-1", "kind": "simulated",
             "preferred_foot": null, "weak_foot": null}}
```

The request carries a **snapshot id, not a frame**. The server resolves the
frame from the match's own decision records and checks the id, so a client
never holds the actual action, the outcome, or any future frame.

The response carries `status`, `candidate_set_id`, `data_version`,
`profile_version`, `candidates`, `evidence`, `explanation`, `agent_trace` and
`limitations`.

The rules the contract keeps:

- `status` is one of `ready`, `partial`, `unknown`, `model_unavailable`, `error`.
  A model failure returns `model_unavailable` with the comparison intact.
- `candidate_set_id` is derived from the snapshot, the data version, the profile,
  the candidates and the evidence. When it does not match the set the interface
  is holding, the interface discards the agent answer.
- `opportunity` and `main_risk` are derived from computed values, never written by
  the model. No value gain, scenario weight or success percentage is shown, because
  a rule assumption is not a probability.
- `agent_trace` records role, tool, milliseconds and success. No key, no prompt
  and no provider body appears in it.
- `check_exchange` refuses a stale snapshot, a mismatched candidate set, a
  dangling citation, a rank that is not contiguous, or a pass whose receiver is
  not an active teammate. A refusal is a transport error, never a fabricated
  response.

One check the schema cannot do lives in `decision/agents.py`: the schema
validates structure and cannot read prose, so a response whose answer quotes a
model internal ("value gain around 0.059") is marked `partial` with the claim
named, instead of reaching the interface as if it were a probability.

The agent half of the same request is `POST /api/decision-analysis/agents`,
which takes `{request, candidate_set_id}` and returns the `explanation` and the
`agent_trace` for that candidate set.

```sh
npm run test:contract        # the pinned cases and the schema
npm run validate:schema      # every record in the data against the schema
```

#### Comparing a single agent with the team

To record where the team differs from one agent, run the same snapshot and
question through both and read the two answers side by side:

```sh
# Pick a decision id from the match's decisions.jsonl
python3 -m decision.agents --match PL26-W01-BHA-MUN --decision d000001 \
  --question "Why not pass to the striker?"
```

It prints the single-reviewer text, the team's answer with its verdict and
cited evidence ids, and the roles that ran. The single reviewer sees the same
computed comparison but cannot audit its own prose; the audit role is what
rejects an unsupported claim. Record one concrete difference per demo case
rather than claiming a general improvement.

### Post-match analysis agent

The project interface, generated reports, documentation and agent prompts are in English. The Coach page keeps one deliberate exception: a language toggle that switches the explanation to Chinese.
`analysis_agent.py` runs automatically from `write_match()` after each simulated match ends.
It checks the final whistle, event count, match identity and goal sequence before analysing
the entire event stream. Each match receives an `analysis.json` file, including matches
with only a 60-second tracking preview. Existing finished matches have reports too.

Open **Analysis** to read and export the final report at any replay position. A full-time
banner links to the report when the full replay finishes. A preview ending does not count
as a final whistle. Reports do not change the replay's time-filtered event feed.

The default **local evidence agent** uses deterministic English reporting and transparent
impact scoring; it is rule-based, not an LLM. It considers every player who appeared,
including substitutes and goalkeepers. Goals, non-goal shots on target, saves, interceptions,
passing and cards contribute to the award. The exact formula and tie-break order appear in
each report. Pressure tags, distance, unrecorded assists and xG are not used to infer quality
or tactical intent. These are simulated matches and the award is a demo assessment.

```sh
# Generate or refresh reports without rerunning the simulation
npm run analyze

# Analyse a single completed match
python3 analysis_agent.py data/league/matches/<match-id>

# Explicitly regenerate cached reports
python3 analysis_agent.py --force
```

For model-written English summaries and half-by-half analysis, set `OPENAI_API_KEY` and
`OPENAI_MODEL` in the generating process's environment, then use:

```sh
python3 analysis_agent.py --mode openai

# Also use model narration automatically for newly generated matches
TOUCHLINE_ANALYSIS_MODE=openai python3 generate.py
```

Choose a model supporting the [Responses API structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Model mode sends the derived match evidence (including player names, statistics and event
references) to OpenAI. Credentials remain in the Python process and are never included in
browser code or reports. The model writes the narrative; the evidence, ranking and award
remain computed and auditable. Generated prose can still contain mistakes.

Reports are cached by source fingerprint, agent version, mode and model. Missing
configuration, timeout, refusal or malformed responses retain the local report with a
visible explanation. Run the same analysis command to retry. Local mode requires no
credentials, network, packages or background service.

### Squad data

`data/league/squads.json` is written by `generate.py`. It contains 20 fictional clubs and 560 fictional players (28 per club), including shirt number, position, detailed position, a procedural nationality, date of birth and age at 2026-10-19.

Match lineups are selected from those generated squads by position, then supplemented with substitutes. The match simulation still determines results, events, cards and tracking. No official squad list is copied.

## Repository layout

```text
data/league/
├── league.json              # clubs, fixtures, results, table, scorers, summary
├── fixtures.jsonl           # one JSON fixture per line
├── standings.json           # league table
├── squads.json              # 20 fictional 2026/27 squads
├── validation_report.json   # league consistency report
└── matches/
    └── NW26-W03-.../        # sample match; full tracking is optional
        ├── metadata.json
        ├── summary.json
        ├── analysis.json    # English report, award, ranking and source evidence
        ├── events.jsonl
        ├── states.jsonl
        ├── preview-60s.json
        └── tracking.jsonl   # only for featured/full matches

data/                      # legacy single-match example used by validate.py/package.py
index.html
styles.css
app.js
core.js
tracking-worker.js
generate.py
analysis_agent.py
validate.py
validate_league.py
package.py
schema.json
```

## Generate the league

The default league is 20 clubs × 4 matchweeks × 10 matches = 40 fixtures. Every club plays once per matchweek and ends with 2 home / 2 away matches.

```sh
# Default: 4 matchweeks, full tracking for the marquee match of each week
python3 generate.py

# Change the number of matchweeks (1-19) or the tracking scope
python3 generate.py --weeks 4 --tracking featured
python3 generate.py --weeks 4 --tracking all
python3 generate.py --weeks 4 --tracking none

# Add a full replay for a specific fixture
python3 generate.py --full-match NW26-W01-HBR-MTN

# Rewrite the league index but keep only the two sample match directories
python3 generate.py --weeks 4 --tracking none --retain-matches 2

# Generate an alternate league with a different seed
python3 generate.py --seed 12345 --output data/league-alt
```

`--tracking` controls full 5 Hz tracking:

| Value | Meaning | Approx. size (4 weeks) |
| --- | --- | --- |
| `featured` (default) | Full tracking for the highest-rated fixture each week; 60s previews elsewhere | ~300 MB |
| `all` | Full tracking for all 40 matches | ~1.3 GB |
| `none` | No full tracking; previews, events, states and summaries only | ~190 MB |

Fixtures run from Saturday 24 October 2026 across four weekends, with local kick-off times in `Europe/London`. The schedule uses the first four rounds of a single round-robin rotation, so no pairing repeats.

## Data model

Each match keeps the existing `HOME / AWAY` stream format:

- 28 registered players per team: starters `H01–H11` / `A01–A11`, substitutes `H12–H14` / `A12–A14`.
- 22 players + 1 ball in tracking frames while nobody is sent off.
- 5 Hz sampling: 30,001 frames from `0` to `6,000,000` ms (100 simulated minutes).
- 6,001 one-second state snapshots.
- `metadata.json` maps `HOME`/`AWAY` to fictional clubs and includes player names, shirt numbers, positions and squad status.
- `summary.json` includes final score, statistics, goals and per-player distance.
- `events.jsonl` includes passes, carries, pressure, interceptions, shots, saves, restarts, cards, substitutions and match phases.
- `tracking.jsonl` is written only when full replay is requested.

The root `data/` folder remains the original two-team Harbor FC vs Mountain FC example. The frontend uses `data/league/`; the root data is retained for the legacy single-match validator and packaging script.

## Event generation

- `Match.emit()` — builds every event with `event_id`, `sequence`, `match_id`, `period`, `start_ms`, `end_ms`, `available_at_ms` and `possession_id`.
- `Match.finish_action()` — emits `carry`, `pass`, `interception`, `shot`, `save`, `stoppage` and `restart` events.
- `Match.step()` — emits `pressure`, `period_start`, `period_end`, `match_end` and `action_cancelled`.
- `Match.set_possession()` — emits `possession_change`.
- `Match.apply_administrative_events()` — emits yellow cards, red cards and substitutions.
- `build_summary()` — extracts goals from `shot` events with `outcome="goal"`.
- `write_match()` — writes each match's `events.jsonl`.
- `generate_league()` — creates each match and calls `write_match()`.

Events are only released when `available_at_ms <= replay time`. The replay never reveals future passes, cards, substitutions or goals.

## Validation

```sh
npm test

python3 validate.py
python3 validate_league.py
python3 validate.py data/league/matches/<match-id>
```

`validate.py` checks a single match and requires `tracking.jsonl`: 5 Hz continuity, identities, pitch bounds, velocity/acceleration limits, ball attachment, event causality, goals, statistics and state snapshots. The checked-in sample omits tracking files, so generate one before running it. `validate_league.py` checks the 20-club schedule, every match directory's summary/events/states/preview, the table, scorer totals and that match lineups come from `squads.json`. It fails on the trimmed sample because 38 match directories are not checked in.

## Data sources and attribution

Everything analysed here is synthetic.

- **Matches, events and tracking** are generated by `generate.py` and
  `scripts/synth/`. The league is the *NextPlay League*, season 2026/27, with
  twenty fictional clubs and fictional grounds. The upstream generator, the
  imported commit and the absence of an upstream licence are recorded in
  [`SOURCE.md`](SOURCE.md).
- **The trained decision model and the 40-match decision dataset** in
  `data/decision-analysis/` come from the same upstream family. The source
  lock is `data/decision-analysis/source-lock.json`; `python -m
  decision_analysis.pipeline validate` re-checks the committed dataset against
  the contract without writing to it.
- **Position-value calibration and the pass / shot frequency baselines**
  reference [StatsBomb Open Data](https://github.com/hudl/open-data)
  (© StatsBomb, published under its own open-data terms). StatsBomb is not a
  sponsor of this project and none of its match data is redistributed here.
  The matches analysed in this repository are synthetic; only the frequency
  reference is real.

## Limitations

This is a demo, not a professional football model. It does not model offsides, a complete foul/referee system, physical collisions, fatigue or full ball physics. Cards and substitutions follow a deterministic demo script; substitutes inherit the outgoing formation slot; pressure is a proximity heuristic. Match outcomes are heuristic and are not calibrated to real football distributions. Use the label **simulated match data** whenever presenting scores, distances or tactical explanations.

Squads, clubs and grounds in this tree are fictional. Match events, tracking and results are generated. Do not present them as official competition data.

### Daily calendar

The homepage includes a seven-day schedule and an expandable January calendar,
with an All clubs / My club filter. The calendar uses January 2027 within the
2026/27 season and the existing simulation clock (`CURRENT_MATCHWEEK = 3`), so
“This week” is January 11–17 rather than the computer's current week. The four
rounds occupy January 2–3, 9–10, 16–17 and 23–24, with five matches each Saturday
and Sunday. Unscheduled dates remain empty, including the final weekend.

`calendar.js` maps the source fixtures to these simulation dates at load time;
the original generated replay files remain source data. The homepage, match
picker and match header share the mapped dates. Only prior rounds show scores
and report links in the calendar. Calendar coverage and score visibility are
checked by `tests/calendar.test.js` as part of `npm test`.

## Replay desk

The match replay is the screen. The left board shows the clicked player or a team’s totals. The right board accepts a question only after the replay is paused on a decision. The separate three.js pitch is not part of this page.
