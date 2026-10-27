# NextPlay AI — submission summary

**Track:** Best multi-agent system (Microsoft "Inside the Game" hackathon)

## What it is

NextPlay AI freezes a football match at the moment the ball reaches a player and
answers the question a coach or a fan actually asks: *what were the options, and
what did each one cost?* It does not grade the player. It shows the choice set
that existed, the risk on each route, and what a short rollout of an alternative
would have looked like.

The product is a working web application, not a mock-up: 40 synthetic matches,
91,031 registered decision snapshots, four trained fold models, and a live
model-backed agent team.

**Live instance:** <https://nextplay-ai.azurewebsites.net/index.html?match=PL26-W01-MCI-CHE>

That link opens a match with the replay desk on screen. The model key is held
by the instance, so the four-role team answers without the visitor supplying
anything. The three fixed cases are at
<https://nextplay-ai.azurewebsites.net/cases.html>. The deterministic Q2 comparison needs
no model key. AI narration uses the configured service.
The local product entry is `index.html?view=decisions`; deployment is not performed by this change.

## The five challenge stages, and where each lives

| Stage | What the product does | Where |
| --- | --- | --- |
| Ingest synthetic events | A generator produces matches, events, tracking and per-match decisions from a fixed seed | `touchline/generate.py`, `touchline/scripts/synth/` |
| Interpret as statistics and context | A frozen snapshot becomes a ranked candidate set with an evidence registry | `touchline/decision_analysis/input_adapter.py`, `comparison.py` |
| Explain why it matters | Each candidate carries a written opportunity and main risk, derived from the computed values rather than written by a language model | `touchline/decision_analysis/comparison.py` |
| Render to the screen | Replay plus an independent Workspace Decision Analysis with the exact snapshot, candidate ranking, Counterfactual and four-role AI coach | `touchline/index.html`, `touchline/decision-analysis-view.js`, `touchline/replay-desk.js` |
| Personalisation | Fan / Analyst modes request different levels of explanation to the same moment, and the interface switches between English and Chinese | `touchline/decision/agents.py`, `touchline/coach-i18n.js` |

## Microsoft and Azure technology actually used

- **Azure AI Foundry** hosts the language model. `gpt-4.1-mini` is deployed in
  `germanywestcentral` on an Azure AI Services account. The server holds the key
  and sets a daily call cap, so a judge can exercise the product without
  supplying a key. Referenced in `src/inside_the_game/system2/foundry.py`
  (`FOUNDRY_PROVIDER = "azure-ai-foundry"`) and `touchline/model_service.py`,
  which sends both `api-key` and a bearer token to a Responses-compatible
  endpoint configured by `ITG_MODEL_BASE_URL` / `ITG_MODEL_NAME`.
- **Microsoft Agent Framework** (`agent-framework-core` 1.22.0) runs the
  four-executor decision workflow in
  `src/inside_the_game/system1/agent_workflow.py`: `read-frame` → `decide` →
  `score-completion` → `narrate`, wired with `WorkflowBuilder` over
  `agent_framework.Executor` classes that pass artifacts through the framework's
  own state store rather than Python closures. Each executor degrades on its own
  and records the degradation, so a lost step is visible instead of silent.
- **GitHub Copilot** was used as the development assistant across the team.

Azure deployment beyond the Foundry resource (Container Apps, AKS) is **not**
part of this submission. The old Public Demo bundle is retired with HTTP 410; the shared synthetic data and independent deterministic Q2 analysis remain available.

## The four-role agent team

`touchline/decision/agents.py` runs one model deployment with four distinct
system contexts against a single shared, hash-identified snapshot:

| Role | Job | Required tool |
| --- | --- | --- |
| coordinator | understands the question, delegates in a fixed order, merges the answer | — |
| attack | argues the forward options | `compare_actions` |
| defense | argues what the defenders do | `simulate_action` |
| reviewer | checks every number, source and overreaching claim | `check_evidence` |

Rules the runtime enforces rather than asks for: the delegation order is fixed;
each specialist must call its own tool before answering; a reviewer rejection
sends the answer back to the coordinator exactly once, and a second failure
returns the computed comparison alone; every cited id must exist in the public
evidence registry, so private model internals cannot be quoted; the trace records
role, tool, elapsed time and success, and never records the key.

A real run over the first match takes about 24 seconds and produces a trace such
as `attack → coordinator → defense → coordinator → reviewer → coordinator`, with
the answer citing evidence ids the browser can resolve.

## Honesty constraints the product enforces

- The ranking is a **decision aid**, not a probability. `value_gain`, the
  scenario weights, the sensitivity ranges and the four-way shares are model
  internals and are deliberately not printed in any interface; the screen shows a
  rank and two sentences of reasoning. The contract's own rule is that
  `status` reports `model_unavailable` and the computed comparison still stands
  when the model is unreachable.
- Revealing the actual outcome never changes the pre-action ranking.
- Every assumption is labelled where it appears: unvalidated lane rule, hand-set
  retention weight, no preferred-foot or body-orientation knowledge.
- All matches, clubs, grounds and players are fictional. Real competition data is
  used only as a statistical reference for calibration, with attribution.

## Repository map

| Path | What it is |
| --- | --- |
| `src/inside_the_game/` | System 1 softmax policy, System 2 narration, synthetic generator, Agent Framework workflow |
| `touchline/` | The web application: server, contract, decision analysis, agent team, front-ends |
| `touchline/data/decision-analysis/` | The trained model layer: four fold models, 40-match scored and snapshot datasets, training report, manifest |
| `touchline/contracts/` | The JSON contract, its schemas and the validators |
| `docs/media/nextplay-demo.mp4` | The demo recording, 1 minute 37 seconds |

## Reproduce

```sh
cd touchline
python3 -m decision_analysis.pipeline validate   # re-checks the committed dataset
node scripts/validate_contracts.mjs --dataset data data/league
node scripts/validate_decision_analysis.mjs
python3 -m pytest tests/ -q
```

`python3 server.py` serves the application on port 5173.
