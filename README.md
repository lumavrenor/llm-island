**English** | [日本語](README.ja.md)

# llm-island

An island simulation where 100 residents wander around and talk with whoever
they run into, all driven by a local LLM. Through those conversations they
spread rumors and cheer each other up. Now and then an evil monster arrives
from beyond the island. The residents run from it, fight it, or go to rescue
friends it has frozen. What each resident says, where they go, and who they
help is decided by that resident's own LLM calls.

[![llm-island demo video (YouTube)](https://img.youtube.com/vi/LGSwWh7aHrw/hqdefault.jpg)](https://www.youtube.com/watch?v=LGSwWh7aHrw)

▶ Demo video (YouTube): https://www.youtube.com/watch?v=LGSwWh7aHrw

This is a personal hobby project. I don't respond to questions or requests.
However, reports of rights/licensing concerns or problems are welcome via GitHub Issues.

Written entirely in Python. The 3D display runs on the
[Ursina](https://www.ursinaengine.org/) engine. The residents, swords, magic
staffs and the monster are all built in code, with no external model files.
The clay-style 3D characters and the BGM come from the sister project
[llm-radio-daemon](https://github.com/lumavrenor/llm-radio-daemon).

By default the residents live in Japanese, but they can be switched to English
(see [Language](#language-japanese--english)). Developer-facing logs stay in
Japanese either way.

## What this project is (and isn't)

This is not practical software. It's an experiment for a programmer to play
with on their own machine. The question it asks is: what happens when you run
100 LLM residents at once on the inference server of a single PC?

- How far does a rumor travel, and through whom? How does its content change along the way?
- Does a resident who was rescued remember who saved them, and tell others about it?
- When the monster shows up, do residents flee or fight? Who does a healer save first?

It isn't a game. There is nothing for a player to control; the screen is for
watching. The aim is to see *why* the LLM decides what it does, rather than to
hard-code the residents' behavior.

## About what the LLM generates (important)

Every line the residents speak, their inner voices, the rumors, and the
monster's lines are fiction, generated on the fly by a local LLM. None of it is
checked by anyone. An LLM can ignore its instructions or say something wrong or
inappropriate in a perfectly confident tone, and current generative AI
technology cannot bring that risk to zero.

- Don't take anything the residents say as fact or advice.
- The author is not liable for any damage arising from this software's output.

## Features

- **100 residents on the LLM at once** — Instead of a thread per resident, every
  request that needs an answer is collected into a "wave" and sent to the
  inference server in one go, so the server's batching is used to the full.
- **Conversation and memory** — Two residents who meet take turns, one line per
  request. After a conversation the LLM writes a summary, and the resident
  remembers how they feel about the other one and any rumors they heard
  (SQLite). Those memories go into the prompt the next time they meet.
- **Rumor spreading** — Residents pass on what they heard about other
  residents to yet another resident. `report.py` shows how many hops each rumor
  travelled and who passed it to whom.
- **Monster, warriors and healers** — From time to time the monster
  "Gloomwraith" appears and freezes residents with its claws. Warriors fight it
  with psychic shots, and healers thaw frozen residents with a magic staff. The
  monster also uses the LLM to decide whom to hunt and when to leave.
- **HP, heart and status effects** — Residents have HP and a heart (morale).
  Frightening events lower the heart until they become "scared". Staying near a
  music-box tower or being cheered up in conversation restores it.
- **Picks up where it left off** — World time, positions, HP, hearts and
  memories are saved to `world.db`, and the next run continues from there.
- **Runs without an LLM** — `--stub` uses dummy replies, so you can check how it
  works without a GPU.

## What you need

- **Windows 10 / 11** (tested on Windows 11)
  - The viewer has only been checked on Windows. It looks up a Japanese font
    only among the Windows system fonts, so on Linux / macOS Japanese text in
    the viewer won't display correctly. `start.sh` itself runs on Linux / macOS,
    and `--headless` doesn't need the font.
- **Python 3.11 or later** (the author uses 3.14; `tomllib` needs 3.11)
- **An inference server with an OpenAI-compatible API** (the author uses
  [SGLang](https://github.com/sgl-project/sglang))
  - It must support structured output with JSON Schema (`response_format` of type `json_schema`)
  - Requests for all 100 residents are sent at once, so a server built for
    concurrent batching (SGLang, vLLM) suits it best
  - The author runs Qwen3.8-27B (NVFP4) across 3 GPUs with pipeline
    parallelism (PP3). Other models are untested, but a smaller model may
    let the same VRAM handle more residents (`--npcs` reduces the count)

### Setting up the inference server

How to install an inference server varies a lot with the GPU (NVIDIA
generation or AMD Radeon), VRAM, CUDA/ROCm version and OS (WSL2 on Windows).
Copying the author's steps will not necessarily work on another PC. The most
reliable route is to have a coding agent such as Claude Code set it up while
inspecting your machine. Let it read "Game workload" and "Author's setup" below
as well; they help it choose the values. For example:

> Install SGLang on this PC (or vLLM if SGLang does not suit the GPU) and serve
> an OpenAI-compatible API at `http://127.0.0.1:30000` with
> `--served-model-name npc`. Structured output with JSON Schema
> (`response_format` of type `json_schema`) must work. Pick a Qwen3-family
> model and quantization that fit the GPU and VRAM, and tune concurrency for
> the workload described under "Setting up the inference server" in README.md.
> Finally, check that `python tools/gen_personas.py` succeeds.

`gen_personas.py` sends requests for all 100 residents in a single wave, which
makes it a good server check (it does not touch a DB that already has residents
unless you pass `--force`).

#### Game workload

| Item | Value |
|---|---|
| Pattern | Requests for every resident that needs a reply are sent at once as a "wave" (up to 100; `[llm] max_concurrency` in [config.toml](config.toml)) |
| Prompt | About 840 tokens on average (persona, memories, situation) |
| Reply | Structured JSON Schema output, at most 100–160 tokens (700 for persona generation only) |
| Thinking | Always off (sent with `chat_template_kwargs: {"enable_thinking": false}`) |

Many requests with long prompts and short replies arrive together, so speed is
decided less by single-request generation speed than by how much prompt
processing (prefill) the server can batch.

#### Author's setup

- RTX 5060 Ti 16GB × 3 (48GB total, no P2P, PCIe; one card also drives the
  display) / WSL2 / SGLang 0.5.21
- Qwen3.8-27B NVFP4 with 3-stage pipeline parallelism (PP3), 48 concurrent

```bash
CUDA_VISIBLE_DEVICES=1,2,0 \
SGLANG_PP_LAYER_PARTITION=18,24,22 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
python -m sglang.launch_server \
  --model-path Qwen3.8-27B-NVFP4 --served-model-name npc \
  --tp-size 1 --pp-size 3 \
  --context-length 8192 --mem-fraction-static 0.93 --kv-cache-dtype fp8_e4m3 \
  --max-running-requests 48 --max-queued-requests 192 \
  --cuda-graph-max-bs-decode 48 --disable-prefill-cuda-graph \
  --disable-radix-cache --reasoning-parser qwen3 \
  --host 127.0.0.1 --port 30000
```

What the author found (the reasoning carries over to other setups):

- **Concurrency (`--max-running-requests`) matters most**, and bigger is not
  faster. Most of Qwen3.8's layers use linear attention, which keeps a large
  per-request state. The server reserves that state for every concurrent slot
  at startup, and what remains becomes the KV cache. At 100, the KV cache ran
  short and only about 9 requests actually ran at once; 48 was faster. Choose
  it so that `max_total_num_tokens` (KV capacity) in the startup log is well
  above "concurrency × ~1,000 tokens"
- Requests beyond the concurrency limit wait in the queue
  (`--max-queued-requests`). A wave is at most 100 requests, so as long as
  concurrency + queue exceeds 100, nothing overflows into errors
- Set `--cuda-graph-max-bs-decode` equal to the concurrency; if it is smaller,
  batches above it run several times slower
- `--disable-radix-cache`: with this model, enabling the prefix cache capped
  concurrency at a few requests, so it is off (for an ordinary model without
  linear attention, leaving it on may be faster)
- Without P2P between the GPUs, tensor parallelism (TP2) ran at about a quarter
  of the speed of PP3. With NVLink or P2P, TP may be faster
- `--context-length 8192` is enough
- vLLM 0.29.0 was also tuned to the same layout (PP3, 48 concurrent) on the
  same machine and model, and it was slower than SGLang, handling about 60% of
  the throughput (100 requests sent at once all came back in 28 s on SGLang,
  73 s on vLLM). With this model vLLM's KV block is a large 1,568 tokens, and
  the prefix cache did not help either. This comparison used only load-test
  scripts that mimic the game; the game itself has not been run on vLLM

#### Other GPUs

The author has only tested the 48GB setup above. **Whether 100 residents run
on 32GB or 16GB of VRAM is untested.** The points below are only hints:

- **NVFP4 needs an RTX 50 series (Blackwell) or newer GPU.** On RTX 40 / 30
  series you will probably need a model with another quantization such as AWQ
  or GPTQ. On GPUs without FP8 support (RTX 30 series, etc.), you likely need
  to leave `--kv-cache-dtype` at its default (bf16) too
- **AMD Radeon** will probably mean a ROCm build of SGLang or vLLM (not tried
  by the author)
- With less VRAM, a smaller model (Qwen3-8B / 14B, etc.) seems worth trying.
  Lighter weights leave more memory for the KV cache, so it may even serve
  more residents at once (reply quality may drop). If it is still too heavy,
  you can reduce the residents (`python main.py --npcs 20`). If replies are
  slow, also revisit `[llm] timeout_sec` (per-request cutoff) in
  [config.toml](config.toml)
- The same reasoning should apply to vLLM (concurrency is `--max-num-seqs`)

The simplest way to start it by hand (pick a model that fits your GPU memory):

```
python -m sglang.launch_server --model-path Qwen/Qwen3-8B --served-model-name npc --host 127.0.0.1 --port 30000
```

The connection settings are under `[llm]` in [config.toml](config.toml)
(`base_url` and `model`). Qwen3's "thinking" is always turned off.

## Setup (Windows / PowerShell)

```
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\activate
```

`start.bat` (`./start.sh` in Git Bash) does the first two lines (create the
venv and `pip install`) for you if `.venv` doesn't exist yet, and if world.db
has no residents it generates the personas (`gen_personas.py`) first. So
`start.bat` / `./start.sh` alone is enough to get going. The `python ...`
commands below assume the `.venv` is activated.

## Running

```
python tools/gen_personas.py                 # generate the 100 personas into world.db (once, first; optional)
python main.py                         # viewer
python main.py --headless              # no viewer (logs and metrics only)
python main.py --headless --minutes 30 # stop after 30 minutes
python tools/report.py                       # stats (how far rumors spread, rescues, raid results, ...)
```

| Option | What it does |
|---|---|
| `--stub` | Use dummy replies instead of the LLM (for checking the plumbing; also `gen_personas.py --stub`) |
| `--speed 8` | Run world time 8x faster when headless (for balancing with the stub) |
| `--npcs 20` | Fewer residents |
| `--fresh-memory` | Erase memories and world state and start a new world |
| `--minutes 30` | Quit after 30 minutes of world time since this launch |
| `--db PATH` | Use another file instead of `world.db` (`world_en.db` in English) |
| `-v` | Also log the inner voice (the `manner` of movement intents) |

`start.bat` (`./start.sh` in Git Bash) runs `main.py` with the `.venv`
Python and passes its arguments through (creating `.venv` first if it's
missing).

Each launch **continues from the world as it was when you last quit** (world
time, residents' positions, HP, hearts, status effects, memories, and the raid
count; saved to `world.db` every 3 seconds and on exit). To start a new world,
erase the data first:

```
reset.bat           # erase memories and world state (keeps the personas). ./reset.sh in Git Bash
reset.bat --all     # delete world.db entirely (the next launch regenerates the personas)
```

Stub runs (`--stub`) also advance the same `world.db`. To keep your real world,
point `--db` at a copy of `world.db`.

## Language (Japanese / English)

The residents can live in Japanese or English. Set it at the top of
[config.toml](config.toml):

```toml
[locale]
lang = "en"    # "ja" / "en"
```

This switches the residents' talk, their names (from `names_en.txt`), the place
names, the monster's name, the prompts, and the viewer's text. Settings that
differ by language are written as `{ ja = ..., en = ... }` in config.toml.

Personas and memories are written in the language they were created in, so each
language keeps its own database (`[world] db_file`: `world.db` for Japanese,
`world_en.db` for English). The first time you switch, create the residents for
that language:

```
python tools/gen_personas.py      # with lang = "en", writes world_en.db
python main.py
```

`main.py` refuses to start if the database was created in the other language.
Developer-facing logs (`log/island.log`, `python tools/report.py`) stay in Japanese.

## Viewer controls

| Input | What it does |
|---|---|
| Left drag / WASD | Pan (returns to the auto camera after 20 s without input) |
| Right drag / wheel | Rotate / zoom |
| Click | Follow that resident and show their info panel |
| Esc | Back to the auto camera (director) |
| V | Toggle inner voices |
| M | Toggle sound (BGM and effects) |
| Shift+Q | Quit |

The auto camera scores what is happening on the island (conversations,
rescues, raids, ...) and shows the most interesting spot. The second line of
the HUD shows the model name and version the inference server reports.

## How the LLM is driven (waves)

```
collect ─▶ wait ───────────────▶ play ─▶ collect ...
 send all   wait until all         apply the results together,
 at once    return (world keeps    then wait long enough for
            moving)                the lines to be read
```

- At most one request per resident per wave (speech > rescue decision >
  movement intent). Post-conversation summaries and the monster's decision
  (one) ride along in the same wave
- One line of dialogue = one request. Two residents take turns, one wave each
- The only background thread is the one for HTTP. Results are applied on the
  main thread, a wave at a time

## HP, heart and status effects

- HP doesn't drop in everyday life; only the monster's attacks lower it. At 0
  the resident is **frozen** (trapped in a block of ice and unable to move)
- The heart drops from the monster's attacks, from the "noise" those attacks
  leave behind, and from seeing a friend freeze right in front of them. It
  recovers near a **music-box tower** and when **cheered up** in conversation

| Status | When | Effect | Look |
|---|---|---|---|
| Freeze | HP 0 | Can't move. Only a healer's staff thaws it (wakes with full HP) | Ice block, pale blue |
| Noise | Hit by an attack (extended on each hit) | Heart drains slowly for a while | Purple flicker |
| Scared | Heart below a threshold | Shows up in the prompt (a reason to flee or go to a tower) | Bluish and trembling |

Settings: `[npc]` / `[solace]` in [config.toml](config.toml).

## The monster, warriors and healers

Now and then a single large black monster, "Gloomwraith" (ヤミゴースト in
Japanese), appears at the edge of the island. When its claws reach its target
it takes HP and heart (an ordinary resident freezes after 3 hits), and after
freezing enough residents it leaves, full. **Whom to hunt and when to leave are decided by Gloomwraith's own LLM
calls.**

5 of the 100 residents are **warriors** (gold names, carrying swords) who wear
down the monster's HP with psychic shots. Gloomwraith fires back at any warrior
who shoots it.

Only the 3 **healers** (light-green names, carrying magic staffs) can thaw a
frozen resident. Once a healer decides to, it raises its staff and chants, and
the frozen resident wakes up with full HP. Healers sense a freeze anywhere on
the island and use the LLM to decide where to go.

- Whether a resident flees or fights (warriors only) is decided by the LLM as a movement intent
- Settings: `[raider]` / `[warrior]` / `[healer]` in [config.toml](config.toml).
  See [sim/raid.py](sim/raid.py) (monster, warriors) and [sim/heal.py](sim/heal.py) (healers)
- `python tools/report.py` lists each raid's outcome (driven off or not, how many
  were frozen, each warrior's hit rate) and Gloomwraith's decisions

## Resident looks (3D characters)

Ported from llm-radio-daemon's clay-style characters
([viewer/poly_character.py](viewer/poly_character.py)): 6 hairstyles, 2 body
types, 4 kinds of accessory. Looks are random but stable per resident, and you
can pin a resident's look with `[[look.npc]]` in [config.toml](config.toml).

```
python -m viewer.preview                 # line up residents 0-9
python -m viewer.preview --catalog       # every hairstyle and accessory
python -m viewer.preview --roles         # warriors and healers (with sword and staff)
python -m viewer.preview --ids 0-4 --raider   # with the monster (size comparison)
```

## Logs

- `log/island.log` … speech, rumors, cheering, rescues, freezes, attacks, per-wave timings
- `log/metrics.jsonl` … per-wave counts, durations, tok/s and TTFT, plus world state every 10 s
- `log/prompts.txt` … prompts and replies for one resident (#0 by default) and the monster

Logs are recreated on every launch.

## For reference: results on the author's machine (2026-10-11)

SGLang (PP3, 48 concurrent), Qwen3.8-27B NVFP4, 100 residents, 30 minutes headless.

| Item | Result |
|---|---|
| Errors / exceptions | 0 |
| Requests | 4,387 in 82 waves, 0 failed |
| Time per wave | median 17 s (median 54 requests) |
| Overall tok/s | median 164 |
| TTFT p50 | median 3.8 s |
| Prompt size | 836 tokens on average |

## Layout

```
main.py            launch (headless / viewer)
config.toml        every setting
start.bat/.sh      launch (creates .venv on first run)   reset.bat/.sh  erase data
core/    config.py (loads config.toml) state.py (state machine helper) run_lock.py (single-instance lock)
tools/   gen_personas.py (persona generation: random seeds, fleshed out by the LLM, 100 in one wave)
         gen_sfx.py (sound-effect synthesis, writes assets/sfx/*.wav) report.py (stats from the DB) reset.py (erase data)
data/    names.txt (candidate resident names; names_en.txt for English)
save/    world.db (world_en.db for English) window.json (window position/size) ... created at run time
lang/              text per language (ja.py / en.py): prompts, situations, event records, stub replies, viewer
sim/     world.py (frame update, waves, damage and freezing) npc.py movement.py encounter.py
         heal.py (rescue) raid.py (monster, warriors)
llm/     client.py (waves, HTTP) stub.py prompts.py schemas.py
memory/  db.py recall.py (memory injection) summarize.py (post-conversation summaries, rumors)
viewer/  app.py bubbles.py camera.py hud.py sound.py poly_character.py weapons.py raider_figure.py, ...
assets/  bgm/ (BGM) sfx/ (sound effects, output of tools/gen_sfx.py)
```

## Credits

The 3D display uses [Ursina](https://www.ursinaengine.org/) (MIT) on top of
[Panda3D](https://www.panda3d.org/) (Modified BSD). HTTP is
[HTTPX](https://www.python-httpx.org/) (BSD-3-Clause) and numerics are
[NumPy](https://numpy.org/) (BSD-3-Clause).

The bundled BGM (`assets/bgm/`) was made by the author for llm-radio-daemon,
with every sound synthesized in code. It contains no external recordings or
samples. The sound effects (`assets/sfx/`) are synthesized in code by
`tools/gen_sfx.py`.

The inference server (SGLang, etc.) and LLM models (Qwen, etc.) are not
included in this repository. Check and follow their own licenses and terms of
use.

## License

Copyright in this software belongs to the author. Running it for personal,
non-commercial use at home is fine. Individuals may also show it in operation
in videos or live streams to introduce, review or explain it, whether or not
the channel is monetized. Publishing or distributing copies or modified
versions, continuously streaming or publishing the software's output as the
main content, and any commercial use are not permitted. See [LICENSE](LICENSE)
for details. This software is provided with no warranty; the author is not
liable for any damage or trouble arising from its use.

The inference server and LLM models this project depends on, and the
libraries listed in the Credits section above, each have their own separate
licenses and terms of use — check those individually.

If anything in this README conflicts with LICENSE, LICENSE takes precedence.
