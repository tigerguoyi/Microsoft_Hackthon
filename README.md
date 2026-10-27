# NextPlay AI

Microsoft × Premier League hackathon entry for the multi-agent award. A viewer pauses a
fictional match and asks what the carrier could have done, and what each option cost.
The screen does not grade the player.

## Current local product (2026-10-27)

Workspace now has independent **Decision Analysis**, **Video Analysis** and
**Real-data validation**. Synthetic Match keeps its unchanged full Q2/models/data.
Private local Video Analysis supports upload, optional YOLO/ByteTrack preannotations,
human revision, partial observation candidates, conditional two-step Q2, visible-defense
sensitivity, shared-motion counterfactuals and the existing four-role Responses coach.
Public/Azure video intake is disabled pending production isolation. No push/deployment.

Read [the current Chinese handoff and limits](HANDOFF_VideoAnalysis_PartialQ2_20261027.md)
and [video API/schema integration](touchline/contracts/VIDEO_ANALYSIS.md).
Real weights were exercised on the supplied UI demo recording and found no mapped
players: **this is a negative control, not successful real-football recognition**.
Authorized real-match positive validation remains outstanding. Manual and API workflows
were tested with explicitly generated fixtures; no paid model calls were made.

Start the ordinary demo with `cd touchline && python3 server.py`; open
`/index.html?view=decisions` or `/video-analysis.html`. Video decoding/CV dependencies
are optional; use the handoff's setup steps for `.[demo]` and local model weights.
No full tracking is checked in; preview animation and full-match decision snapshots
remain available. The historical [Phase 1–3 report](HANDOFF_Phase1-3_20261027.md)
is preserved. Root `inside_the_game` classification research remains separate from
product Q2 and is never the Video Analysis ranking model.

## Judge path

English is the default. Chinese is the second button on the decision flow.

**Hosted instance:** <https://nextplay-ai.azurewebsites.net/index.html?match=PL26-W01-MCI-CHE>

That link opens a match with the replay desk already on screen. The model key
lives in the instance's settings, so the four-role team answers without the
visitor supplying anything. The hosted instance must be redeployed to receive local changes;
`deploy/` holds the existing deployment steps. This task did not deploy it.

To run it locally instead:

```sh
cd touchline && python3 server.py
```

Open http://127.0.0.1:5173/cases.html and walk the three cases: an open-looking pass a
defender can reach first, a shot against one more pass, and a backward pass under
pressure. Each card shows the opportunity and the main risk. Numbers behind the rank
are not printed.

The match page is the product. Open Replay. The left board shows the player you click,
or a team’s totals. The right board stays quiet while the match plays. Pause on a
decision, then ask about that moment.

Azure AI Foundry is the language-model host when the server is configured:

```sh
export ITG_MODEL_BASE_URL="https://<resource>.cognitiveservices.azure.com/openai/v1"
export ITG_MODEL_NAME="gpt-4.1-mini"
export ITG_MODEL_API_KEY="<key>"
```

The key stays on the server. `ITG_DAILY_CALL_CAP` defaults to 200. If the model is
down, the comparison still returns with status `model_unavailable`. The four roles
(coordinator, attack, defense, reviewer) share one candidate set; a reviewer rejection
rewrites once, then the computed comparison is what remains. StatsBomb Open Data is the
calibration reference only, attributed in `touchline/README.md`. Squads in the product
are fictional.

A local recording is `docs/media/nextplay-demo.mp4`. It is not yet a public YouTube or
Vimeo link, and there is no hosted URL that stays up through 10 November without a
machine running the server.

The decision kernel underneath the product is documented from [The decision kernel](#the-decision-kernel).

# The decision kernel

Two things live here. **[`touchline/`](touchline/README.md)** is the product: a fictional
2026/27 league, match replay, the coach page where a viewer freezes a moment and asks
why, a four-role agent team on Azure AI Foundry, and a 3D pitch sample. `src/inside_the_game`
is the decision kernel underneath it.

The decision aid never marks one action as optimal. For a frozen on-ball state it shows
the candidates — passes, carries, a shot when in range, and holding — each with the
computed opportunity and risk, and the full probability distribution over **pass**,
**shoot**, **dribble** and **hold** where the softmax applies.

Start here: [touchline/README.md](touchline/README.md). This file documents the kernel.

The match replay on `touchline/index.html` is the screen: a 2D pitch, a data board, and a question box for the paused decision.

## Locked architecture

1. **Ingest** synthetic match events (JSON/text state).
2. **System 1** maps that state to `P(pass | shoot | dribble | hold)`. The default backend is a lightweight linear softmax over numeric features. It loads `src/inside_the_game/system1/weights.json` when that file is present and otherwise uses the hand-set stub. Those weights are fit on synthetic `decision_point` events only (`docs/v1-model-selection.md`). The same softmax accepts a SynthData tracking frame through `predict_tracking`. An optional [TypeSafe Jev Choice](https://docs.typesafe.ai/primitives/choice) hook accepts the same JSON/text state and is unused when `typesafe-sdk` is not installed. No images. Jev stays off on the MVP path.
3. **Video demo** (`python -m demo.run`) runs detection, ByteTrack, pitch homography, and this same softmax, then paints options on the broadcast. The events path below does not need those dependencies. See [Video demo](#video-demo). The synthetic tracking clip is the primary content; a real broadcast clip is an optional second content source, not the product input.
4. **System 2** turns a decision into a short football rationale. The default is an offline template: no network and no API key. A Foundry narration request is always built, and `inside_the_game.system2.narration.responses_narrator` sends it when a narrator is injected — pointing the base URL at Azure AI Foundry is the only change needed. `touchline/` runs the live four-role team this way; see its README. socceraction xT / VAEP stays a stub sidecar (`TODO`).
5. **Present** emits replay overlay arrows, probability bars for all four actions, and the System 2 explanation in the same overlay.

MVP path in this pull request: **1 → 2 → 4 → 5**.

```
fixtures → ingest → features → system1 softmax → system2 explain → present
                                    ↘ optional Jev Choice (text/JSON, not required)
system2 sidecar: socceraction xT/VAEP TODO (named in the rationale, not fitted)
video: python -m demo.run  (YOLO + ByteTrack + homography + the same softmax)
```

## Install

Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The Jev extra is optional and is not required for the stub or the tests:

```bash
pip install -e ".[dev,jev]"
```

## Run the stub

From the repository root, after install:

```bash
python -m inside_the_game
```

The same entry point is available as `inside-the-game`. It loads `fixtures/synthetic_match_events.json` and prints, for each event, probability bars and arrow placeholders for pass, shoot, dribble, and hold, with the offline explanation on the same overlay. No network calls.

Pass a local model only if you want to replace the template. It must provide `rationale(event, distribution, profile) -> str` and it must not call a hosted API:

```python
from inside_the_game.system2 import explain

explain(event, distribution, local_llm=MyLocalModel())
```

`load_local_llm()` returns `None`. Setting an API key or `INSIDE_THE_GAME_LOCAL_LLM` does not enable a model.

## Video demo

One command reads a broadcast mp4 and writes an mp4 with on-ball options drawn on the pitch:

```bash
pip install -e ".[demo]"
python -m demo.run --input in.mp4 --output out.mp4 --stride 2
```

`--stride 2` runs the player detector on every other frame. The frames in between advance each track with the velocity measured since the last detection (Ultralytics ByteTrack assigns the ids on detection frames). `--pitch-every` (default 15) is how often the keypoint model recomputes the homography.

What you see when someone has the ball:

- One bright arrow for the class the softmax recommends, plus up to two dimmer alternatives. A pass recommendation draws the best visible teammate solid and bright, then the next one or two teammates at low alpha. A dribble recommendation draws one short dashed carry into open space, in a different colour, and at most one dim pass — never a second carry. Shoot and hold stay in the probability bars and are not drawn as lines. A pass whose end is not a teammate visible this frame, or whose shirt does not match the possessor's kit, is not drawn.
- The softmax chooses pass versus dribble versus shoot versus hold. It does not choose the receiver. Pass ranking is forward progress and the space around the lane, with only a light penalty for length, so an open progressive pass can beat a short dump. The carry aims at the best forward gap, not a fixed set of three templates.
- Possession is a small state machine: on the ball, contested, pass in flight, or loose. On the ball, distance, velocity match, and track continuity decide who has it. A fast ball that is not stuck to a foot is a pass in flight: teammates are ranked by who can meet the ball first, and the arrows follow that predicted receiver instead of whichever body the ball is nearest. A touch (the ball reaches a foot and the relative speed drops) commits the switch.
- Arrows are sampled on the 105×68 m pitch and projected back through the homography, so they lie on the broadcast plane. If the pitch model cannot support a homography, the same arrow falls back to a straight line in the image.
- A four-way probability bar sits in the corner. A 2D minimap is on by default (`--no-minimap` turns it off).
- Jersey colours are clustered into two teams. Which side is home is the defensive tail (the deepest outfield players) plus the goal each goalkeeper is standing in, not the average of every shirt. Home defends the left goal and attacks toward x = 105, the same frame as the training features. Pass arrows are pinned to teammates. The shot is pinned to the opponent goal mouth.
- A striped home kit (black and white against neon green) can split across the two colour means, so the home team id drifts and a pass arrow pins an opponent. Lock the kit for that run and cluster 0 stays home. Omit the flag and the defensive-tail 2-means is unchanged.

```bash
python -m demo.run --input in.mp4 --output out.mp4 --home-jersey white-black
```

`--home-jersey` accepts `white-black`, `black-white`, `white`, `black`, `rgb:R,G,B`, or a pair joined with `+` (`rgb:245,245,245+rgb:16,16,16`). Repeat the flag for another sample. The same spec is read from `INSIDE_THE_GAME_HOME_JERSEY` when the flag is omitted. For the Fail-frame clip, pass `white-black` (or two RGB samples from the striped shirt) so pass targets stay on that kit. `TeamBook(home_jersey=...)` is the same lock for an in-process caller.

The six softmax inputs are `ball_x`, `ball_y`, `centrality`, `pressure`, `minute`, `goal_diff`, in that order and in the same units as `weights.json`. `features_from_cv` builds a `MatchEvent` and calls `extract_features`, so a pitch-meter observation cannot drift from training. `--minute` (default 45) and `--score-home` / `--score-away` (default 0–0) fill the two values a broadcast frame does not contain. Pressure is opponent distance on the StatsBomb scale: 0.82 inside 3 m, 0.18 beyond 12 m.

If the pitch model cannot support a homography, the frame falls back to image coordinates: arrows are straight lines in the picture, the bar still runs, and the panel says `image coordinates`. A recent good homography is reused for `--homography-hold` frames (default 30) unless a hard cut is detected, in which case the old matrix is dropped. If the ball detector misses, the last possessor is held for `--hold-frames` frames (default 18) and the ball is coasted; a one-frame jump with low confidence is ignored. The drawn possessor ring sits on a smoothed foot point. A light ball mark is painted only after a few stable detections near those feet, so a noisy box does not drag a dot around the frame. The highlighted action and the primary pass receiver are held across adjacent frames. Dim alternate passes follow the eligible teammates visible on that frame, under the same shirt gate. A player from the other team has to be nearer the ball for several frames before possession, and therefore the goal being attacked, flips. If that goal is outside the picture, the shot tip stops on the frame edge still aimed at it, instead of looking like it ends on a player.

Weights download on first use into `data/models/` (gitignored):

| Role | Hugging Face id |
| --- | --- |
| Players, goalkeepers, referees, ball | [`martinjolif/yolo-football-player-detection`](https://huggingface.co/martinjolif/yolo-football-player-detection) (YOLO11m) |
| Ball bypass when the main detector is unsure | [`martinjolif/yolo-football-ball-detection`](https://huggingface.co/martinjolif/yolo-football-ball-detection) (YOLO11n) |
| 32 pitch keypoints → homography | [`martinjolif/yolo-football-pitch-detection`](https://huggingface.co/martinjolif/yolo-football-pitch-detection) (YOLOv8x pose) |

Tracker: Ultralytics ByteTrack (`bytetrack.yaml`), not a separate weight file. No SportsLabKit, no hosted inference API. CPU is the default (`--device cpu`).

### Clips

The checked-in tree does not contain video. The two clips used to exercise the demo are 1080p, 25 fps, 30 s tactical-camera excerpts circulated with the [roboflow/sports](https://github.com/roboflow/sports) samples. They match the public DFL Bundesliga Data Shootout footage (Kaggle competition data). Use them for research and non-commercial demo only; do not commit them.

```bash
pip install gdown
mkdir -p data/clips
gdown 1OG8K6wqUw9t7lp9ms1M48DxRhwTYciK- -O data/clips/08fd33_0.mp4
gdown 19PGw55V8aA6GZu5-Aac5_9mCy3fNxmEf -O data/clips/2e57b9_0.mp4
```

`08fd33_0.mp4` is the primary end-to-end clip. `2e57b9_0.mp4` pans harder and is the homography stress test. A 10 second preview of the first clip, detecting every second frame:

```bash
python -m demo.run \
  --input data/clips/08fd33_0.mp4 \
  --output preview_08fd33_10s.mp4 \
  --seconds 10 \
  --stride 2 \
  --screenshot-dir preview_frames \
  --screenshot-times 2,5,8
```

The run prints a JSON summary beside the mp4: wall-clock output fps and mean detector time. On this CPU (no GPU, PyTorch CPU, 1080p, `--stride 2`, `--pitch-every 15`):

| Clip | Frames | Wall clock | Output fps | Player | Pitch | Ball | Homography ok | Possessor frames | Of which the ball was held |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `08fd33_0` first 10 s | 250 | 38.3 s | 6.5 | 135 ms | 316 ms | 34 ms | 250/250 | 219 | 168 |
| `08fd33_0` full 30 s | 750 | 103.2 s | 7.3 | 140 ms | 317 ms | 32 ms | 750/750 | 624 | 453 |
| `2e57b9_0` full 30 s (pan) | 750 | 100.2 s | 7.5 | 133 ms | 309 ms | 32 ms | 750/750 | 631 | 472 |

The ball bypass ran on almost every detection frame; the player model's own ball box is often under 0.35 confidence. Possession was still available on about five of every six frames because a miss keeps the last possessor for `--hold-frames`.

These two clips never dropped the homography: the pan in `2e57b9_0` still left enough pitch keypoints, and neither file contains a hard cut (`scene_cuts` 0). A cut, a zoom that hides the markings, or a keypoint fit over the reprojection gate falls back to image coordinates for that frame (the bars and arrows stay up; the panel reads `image coordinates`) instead of stopping. That path is covered by unit tests. Attacking direction follows the deepest outfield players and the goalkeepers' goals, so a team camped in the opponent half is not flipped just because its average x moved forward. The lock can still be wrong if neither side leaves a player near its own goal and both keepers are missed. `--minute` and the score are not read from the broadcast.

## Scheme A shell

The on-ball screen is a web shell in [`web/`](web/README.md): video stage, four-way softmax sidebar, and a timeline of key possessions. It is not a league portal. From `web/`:

```bash
npm install
npm run dev
```

How to point the stage at a local preview, including a file from `python -m demo.run`, is in [web/README.md](web/README.md).

## Tests

```bash
pytest
```

`pytest` checks the four-way distribution with the checked-in weights and with the stub fallback, the tracking path on a synthetic `decision_point` (four-class probabilities, pass targets, carry path), the weight fit on the synthetic sample, the offline System 2 rationale on synthetic states (with the network blocked), the overlay explanation beside all four probabilities, and the synthetic generator's labels. See [DATA.md](DATA.md) and [docs/v1-model-selection.md](docs/v1-model-selection.md) for the v1 softmax, completion score, and Foundry narration.

## Data sources

Every match, every frame and every decision in this repository is synthetic.
Nothing here is a recording of a real match, and no real club badge, kit badge,
crowd image or broadcast footage is included.

| Layer | Source | Licence / attribution |
| --- | --- | --- |
| Match, event and tracking generator | `touchline/scripts/synth/` and `touchline/generate.py`, imported from [LiNTe912/NextPlay-AI](https://github.com/LiNTe912/NextPlay-AI) | Imported with the upstream author's permission for this hackathon. The upstream commit carries no `LICENSE` file, so no SPDX identifier is claimed. See [`touchline/SOURCE.md`](touchline/SOURCE.md). |
| Trained decision model and the 40-match decision dataset | `touchline/data/decision-analysis/`, imported from [tigerguoyi/NextPlay-AI](https://github.com/tigerguoyi/NextPlay-AI), a fork of the repository above | Same terms. The source lock is `touchline/data/decision-analysis/source-lock.json`; `decision_analysis/pipeline.py validate` re-checks it without writing. |
| Club, player and venue names | Fully fictional. Twenty clubs (Aster FC, Beacon FC, Cedar FC, …) with fictional grounds; 560 procedurally generated players | None needed. The upstream squad list was not imported. The upstream three-letter club codes survive only as opaque keys and are never rendered. |
| Calibration reference for spatial values | [StatsBomb Open Data](https://github.com/hudl/open-data) | Used only to calibrate the ground-pass completion and shot frequency baselines. The matches are synthetic; the reference data is not redistributed here. |

## Assumptions and limitations

- The spatial values behind the ranking are **decision aids, not probabilities**.
  `value_gain`, `scenario_weight` and the sensitivity ranges are model
  internals. The interface shows a rank and a written opportunity and risk, and
  deliberately does not print those numbers, so no false success rate or goal
  probability can be read off the screen.
- The decision model's own weights are uncalibrated for shot and carry. Ground
  passes are the only rollout the counterfactual simulates.
- Player foot preference, body orientation and first-touch stability are
  unknown at inference time, so the model cannot use them.
- The synthetic league is generated, not observed. Its numbers describe the
  generator, not football.
- The Foundry narration and the four-role agent team are unavailable when no
  model key is configured. In that case the computed comparison still stands and
  the interface reports `model_unavailable` instead of inventing an answer.
- The daily model-call cap (`ITG_DAILY_CALL_CAP`, 200 by default) bounds the
  hosted demo. When it is spent the comparison is unaffected.

## Attribution

Position-value calibration and the shot/pass frequency baselines reference
**StatsBomb Open Data** (© StatsBomb, published under its own open-data terms).
StatsBomb is not a sponsor of this project, and none of its match data is
redistributed in this repository. The matches analysed here are synthetic.

## Layout

```
fixtures/synthetic_match_events.json
fixtures/synthetic_labeled_sequences.json
src/inside_the_game/
  ingest/          match-event schema, JSON loader, synthetic generator
  features/        event → numeric features
  system1/         softmax policy, fitted weights.json, optional Jev Choice hook
  system2/         offline explain template, optional local model hook, xT/VAEP sidecar stub
  present/         bars, arrow placeholders, and the explanation for all four actions
  pipeline.py      1 → 2 → 4 → 5
scripts/           generate_synthetic, train_softmax
web/               Scheme A shell (video stage, sidebar, possession timeline)
tests/
DATA.md
```

Public entry points other threads can implement against:

- `inside_the_game.ingest.load_events`
- `inside_the_game.features.extract_features`
- `inside_the_game.system1.SoftmaxActionPolicy.predict`
- `inside_the_game.system1.load_jev_choice` / `build_choice_request`
- `inside_the_game.system2.explain` / `load_local_llm` (the loader stays `None`)
- `inside_the_game.present.render_overlay`
- `inside_the_game.run_mvp`

Pitch coordinates in the fixture are meters, x in `[0, 105]` and y in `[0, 68]`, with home attacking toward x = 105.
