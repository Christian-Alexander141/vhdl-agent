# AGENTS.md – Project Rules for VHDL Development

## 1. PROMPT.md has absolute priority (R9)
The file `PROMPT.md` contains the complete, unmodified user request.
- Read it **first** and completely before every task.
- Do **not** change, shorten, summarize, or replace it.
- If a skill or board fact contradicts `PROMPT.md`, **the prompt wins**.
- Record the contradiction in `open_questions` (in manifest) or `reports/review.md`.

## 2. Project Structure (file naming convention)
```
src/<entity>.vhd          # VHDL modules
tests/<entity>_tb.vhd     # Testbenches
constraints/<top>.xdc     # Pin constraints (if any)
reports/                  # Build/simulation/review reports
plan/manifest.json        # OpenCode-generated plan
.opencode_tasks/          # Per-stage task files (internal)
```

## 3. Hard VHDL Rules (from vhdl-synthesis-rules skill)
- VHDL-2008 (`library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;`)
- No `wait` in synthesizable code (only in testbenches)
- No inferred latches – complete sensitivity lists
- One clock domain per process (`clk` + `rst` synchronous)
- Arithmetic only via `numeric_std` (`signed`/`unsigned`)
- Reset style: as `reset_concept` in plan/manifest.json (derived from PROMPT.md); async active-high only if the prompt says nothing about the reset
- Entity name = file name (lowercase, underscores)

## 4. GHDL Commands (used by the pipeline)
```bash
ghdl -a --std=08 src/*.vhd
ghdl -e --std=08 <tb_entity>
ghdl -r --std=08 <tb_entity> --assert-level=error --ieee-asserts=disable-at-0
```
Elaboration and simulation flags are fixed – do not invent new ones.

## 5. Target Board Port Convention (Arty S7-50, {{board_id}})
| Port (case-insensitive) | Pin | I/O Standard | Note |
|---|---|---|---|
| `CLK`, `CLK_100MHZ`, `SYS_CLK`, `CLOCK` | R2 | **SSTL135** (DDR3 clock) | Not a general user clock |
| `RESET`, `RST`, `RESET_N`, `RST_N` | G15 (BTN0) | LVCMOS33 | Active high; `_N` variants inverted |
| `ENABLE`, `EN` | H14 (SW0) | LVCMOS33 | |
| `LOAD`, `LD` | J16 (BTN2) | LVCMOS33 | |
| Other **outputs** (alphabetical) | E18, F13, E13, H15 | LVCMOS33 | Max 4 user LEDs |
| Other **inputs** | – | – | No pin assigned by generator |

The generator in `vivado_synthesis.py` assigns pins by port name. If the prompt requires pins the generator cannot map, write `constraints/<top>.xdc` yourself – the generator will then be skipped.

## 6. Forbidden Workarounds
- Do **not** suppress `NSTD-1` (missing IOSTANDARD) or `UCIO-1` (unconstrained I/O) via XDC severity.
- Do **not** choose top entity by first-file order – use `plan/manifest.json` `top_entity`.

## 7. Skills available in this project
{{skills_list}}

These IDs are **not** registered with any built-in skill tool – that lookup
will fail. Read the file directly with the Read tool instead:
`{{skills_dir}}/<id>/SKILL.md`. The skill description tells you when it is
relevant for the current task.

## 8. Task Completion Protocol
After every OpenCode run, write a one-line file `.opencode_tasks/<task_id>.done.md`:
```
skills: <comma-separated ids you read>
```
This allows the pipeline to verify knowledge usage.