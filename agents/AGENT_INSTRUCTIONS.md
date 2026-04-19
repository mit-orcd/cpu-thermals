# cpu_thermals — agent instructions

A succinct project briefing for any AI coding agent (Cursor, Claude Code, Copilot, etc.) opening this repo for the first time. Read this before making changes.

## What this project is

`cpu_thermals` is a small Linux + macOS Apple Silicon CLI that monitors CPU temperatures live in the terminal and optionally records them to CSV. It is intentionally tiny: the runtime is stdlib-only Python 3.8+, the dependency list is empty, and the CLI surface is three flags. The package is around 600 lines of Python; the examples and CI add another few hundred lines of shell and markdown.

## Non-negotiables (the project's ethos — do not erode without strong reason)

1. **Zero runtime dependencies.** The package installs with `pip install .` and pulls nothing in. Adding `requests`, `pydantic`, `click`, etc. is almost certainly the wrong move; argparse + stdlib `csv` + `subprocess` are sufficient and have been for everything so far.
2. **Tests use no framework.** [`tests/smoke.sh`](../tests/smoke.sh) is bash + `set -euo pipefail` + a 33-line vanilla-Python fake-backend shim. Do **not** introduce pytest, pyyaml, jinja2, or fixtures unless you have a concrete reason that outweighs the loss of "anyone can read the test suite in 60 seconds".
3. **CI is a dumb trigger.** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (15 lines) and [`.gitlab-ci.yml`](../.gitlab-ci.yml) (6 lines) only call `./tests/smoke.sh`. All real test logic lives in the script. This keeps the project portable to any CI provider.
4. **Stdout vs. stderr discipline.** Stdout carries user-facing output (the TUI table, or the CSV when `--csv -`). Banners, summaries, errors, and the Ctrl-C farewell all go to stderr, never to stdout. The pipe-friendly path (`cpu-thermals --csv - | gzip > log.gz`) depends on this.
5. **Per-subdirectory READMEs.** Subpackages and example subdirectories all carry a README using a consistent template (`What this shows / Prerequisites / How to run / What you should see / What to look at next`). When you add a new directory, write its README in the same shape.

## Directory layout (orient yourself in 10 seconds)

```
cpu_thermals/
├── cpu_thermals/                    # the package; ~600 lines stdlib-only
│   ├── cli.py                       # arg parsing + run loop (deliberately thin)
│   ├── backends/                    # WHERE temps come from (one file per platform)
│   │   ├── README.md
│   │   ├── __init__.py              # TempSource Protocol + detect() dispatcher
│   │   ├── lm_sensors.py            # Linux (Intel coretemp + AMD k10temp)
│   │   └── smctemp.py               # macOS Apple Silicon
│   └── output/                      # WHERE temps go (one file per format)
│       ├── README.md
│       ├── __init__.py              # Renderer Protocol + MultiRenderer + select()
│       ├── table.py                 # live colored TUI
│       └── csv.py                   # CSV file or stdout (`-` sentinel)
├── examples/
│   ├── README.md                    # index of examples
│   ├── 1-simple-terminal/           # 5 named scripts + apptainer/ subdir
│   ├── 2-mprime-stress/             # mprime + CSV + apptainer/ subdir
│   └── 3-systemd-csv-rotation/      # systemd unit + logrotate + ansible/ subdir
├── tests/
│   ├── smoke.sh                     # the entire test suite (~140 lines bash)
│   └── fake_run.py                  # 33-line vanilla-Python shim for end-to-end tests
├── .github/workflows/ci.yml         # 15-line trigger; calls tests/smoke.sh
├── .gitlab-ci.yml                   # 6-line trigger; calls tests/smoke.sh
├── pyproject.toml                   # setuptools, console script, no deps
└── README.md                        # top-level user docs
```

## Key abstractions (the only architecture you need to remember)

Two tiny Protocols, two dispatchers, one `MultiRenderer` composite. The whole system fits in a paragraph:

- **`TempSource`** ([backends/__init__.py](../cpu_thermals/backends/__init__.py)) — `name`, `install_help`, `check()`, `read() -> [Reading]`. One implementation per platform. `detect(name=None)` picks one by `--backend` or `platform.system()`.
- **`Renderer`** ([output/__init__.py](../cpu_thermals/output/__init__.py)) — `name`, `start(labels)`, `row(readings)`, `stop()`. `select(tui=, csv_path=)` returns either a single renderer or a `MultiRenderer` that fans `start/row/stop` out to several children. Run loop is unaware of how many destinations are active.
- **`Reading`** — a `NamedTuple(label: str, celsius: float)`. The lingua franca between backends and renderers.

The CSV schema is fixed and long-format: `timestamp,node,sensor,celsius`. One row per sensor per sample. Identical across all backends so files from heterogeneous machines concatenate cleanly. Do not change to wide format.

## How to work on this project

### Always run the smoke tests after a change

```bash
./tests/smoke.sh
```

13 assertions, ~2 seconds. If anything fails, fix it before moving on. The script is self-documenting; read the relevant section to understand what broke.

### Adding a new backend (a new platform / sensor source)

1. Drop a file in `cpu_thermals/backends/` (e.g. `mybackend.py`) with a class exposing `name`, `install_help`, `check()`, `read()`.
2. Register it in `cpu_thermals/backends/__init__.py`: add a small `_make_mybackend` factory and an entry in `_BACKENDS` and (optionally) `_AUTO_BY_PLATFORM`.
3. Update [`cpu_thermals/backends/README.md`](../cpu_thermals/backends/README.md) with one row in the "Current backends" table.
4. Re-run `./tests/smoke.sh`.

The lazy `from .mybackend import ...` pattern in the factory keeps the import graph small (a Linux machine never imports the macOS backend).

### Adding a new output format (e.g. JSON Lines)

1. Drop a file in `cpu_thermals/output/` with a class implementing the `Renderer` Protocol.
2. Wire it into `select()` in `cpu_thermals/output/__init__.py` — usually one new flag in `cli.py` plus one new branch in `select()`.
3. Update [`cpu_thermals/output/README.md`](../cpu_thermals/output/README.md) with a row in the "Current renderers" table and (if the destination is non-trivial) a note in the conventions section.
4. Re-run `./tests/smoke.sh`.

### Adding a new example

1. Make a new subdirectory under `examples/` (e.g. `4-something/`).
2. Write a `README.md` following the `What this shows / Prerequisites / How to run / What you should see / What to look at next` template — copy any existing example's README as a starting point.
3. Any `*.sh` files you add are automatically picked up by `tests/smoke.sh` (it globs `examples/**/*.sh` for `bash -n` + `shellcheck`).
4. If your example ships an Apptainer `.def` or systemd unit or similar artifact, the smoke suite already has grep-based static checks for `.def` files, the systemd unit, and the logrotate config; extend those checks if you add a new artifact type.
5. Add a one-line entry in [`examples/README.md`](../examples/README.md).

### Containerized examples (Apptainer)

Two important rules learned the hard way (see commit `ff13758`):

- **Host-requirements minimum = kernel + modules.** The container bundles all userspace. Do not document `sudo sensors-detect` or other host-side userspace installs as prerequisites; document the actual minimal host ask (e.g. `sudo modprobe coretemp` and the verification one-liner `cat /sys/class/hwmon/hwmon*/name`).
- **Match base image to dynamic linkage.** mprime is glibc-linked, so example 2's SIF must use `debian:12-slim`, not Alpine. cpu_thermals itself is pure stdlib Python and works fine on Alpine. There's a comment block in `mprime-stress.def` explaining this; preserve it.

## Workflow conventions

### Plan before executing for non-trivial changes

When asked for a feature with non-obvious design choices, draft a plan (the Cursor `CreatePlan` tool, a markdown file, or just a structured response) covering: behaviour matrix, code organization, files touched, what's out of scope. Confirm with the user before writing code. The repo has a track record of plan files under `.cursor/plans/` you can scan for tone and depth.

### Commit messages: dense, sectioned, one logical change per commit

Read [`git log`](../.git/) for the established style. Commit messages here are intentionally long and sectioned (Layout / Design choices / Why X / Smoke tested / etc.) rather than terse. They are the primary way someone reviewing the project six months from now reconstructs *why* a thing looks the way it does. Match that style.

Do not amend or force-push without the user's explicit say-so.

### When in doubt, look at how the existing code does it

This project has been built up incrementally with consistent conventions. Patterns to mirror:

- `from __future__ import annotations` everywhere; PEP 604 unions are fine.
- `Optional[X]` from `typing`, not `X | None` in runtime annotations (the codebase mixes both, but Optional is the safer floor for Python 3.8 compatibility).
- Module docstrings (3-5 lines) explaining what the module is for and any platform quirks.
- Public functions and methods carry return-type annotations.
- Banners go to stderr (`sys.stderr.write(...)`); CSV data goes to the configured destination.

## Responsibilities on non-trivial changes

A "non-trivial change" is anything beyond a typo or one-line fix — anything that adds a feature, changes an interface, restructures code, or touches more than ~30 lines across more than one file. For each such change, before declaring it done:

### 1. Update this file when style or practice changes

If you introduce a new convention, pattern, abstraction, or constraint — or change an existing one — update [`agents/AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md) **in the same commit**. The "Non-negotiables" and "Containerized examples" sections both grew this way from real lessons learned (CSV-to-stdout / stderr discipline, "match base image to dynamic linkage", etc.). If you catch yourself writing "I just learned that..." in a commit message, that lesson belongs here too. This file is a living document, not an archaeology project.

### 2. Walk every README.md for consistency

After substantive code or behaviour changes, find every README in the repo and check it:

```bash
find . -name 'README.md' -not -path './.*'
```

For each match, verify:

- **Coverage** — new flags / behaviours are documented where users will look for them (top-level `README.md`, the relevant subpackage README under `cpu_thermals/`, and the relevant example README under `examples/`, as applicable).
- **Cross-links resolve** — no dead `../foo/bar.md` paths after a directory rename or file move.
- **Template still followed** — example READMEs all use the shared sections (*What this shows / Prerequisites / How to run / What you should see / What to look at next*).
- **Behaviour matrices and tables are current** — e.g. the CSV usage table in the top-level README reflects every flag combination.

This is cheap (a few minutes) and catches the most common drift between "what the code now does" and "what the docs say it does".

### 3. Run three sub-agent reviews and address their comments

Before opening a PR or asking the user to commit a non-trivial change, dispatch **three parallel sub-agent reviews** via the host agent's Task / sub-agent tool. Hand each the diff and the relevant files, with the focus below. Treat the comments as a TODO list — address each, or explicitly justify deferring it. Push back when you disagree, with reasoning, and note the round-trip in the commit message body.

| Reviewer | Focus | Asks the reviewer should make |
| --- | --- | --- |
| **Senior software engineer** | Software design, modularity, sensible layering — rather than duplication or repetition. | Is this in the right module? Does it respect the backends-vs-output split? Is there a smaller seam available? Is this a third near-copy of an existing pattern that should be factored out? Are the public Protocols still small enough that a future implementation is a half-page of code? |
| **Software readability + QA** | How easy the code is for a human to follow on first read. Internal documentation. As-simple-as-possible, clear abstractions. | Could a new reader understand the touched files in a single sitting? Does every non-obvious line have a *why* comment (not a *what* comment)? Is intent documented at module / class / function granularity? Are names accurate (`csv_path`, `Reading.celsius`, `MultiRenderer`)? Are error messages actionable? Do the smoke tests cover the new behaviour with one-line clarity? |
| **Experienced CLI UX** | The tool stays very easy to use and understand *without* needing to read extensive documentation. | Does `cpu-thermals --help` still tell the whole story in one terminal screen? Does the default invocation still do "the obvious thing"? Are new flags additive (don't break muscle memory)? Are conflicts handled with a one-line stderr explanation rather than silent override or cryptic error? Are example invocations in `--help` still discoverable? Is the stdout/stderr discipline preserved so existing pipelines keep working? |

Run them in parallel — they're independent, and serializing them costs round-trip time you don't need to spend.

## What to read first

If you have 5 minutes:

1. The top-level [`README.md`](../README.md) — what cpu_thermals does for end users.
2. [`cpu_thermals/cli.py`](../cpu_thermals/cli.py) — the whole orchestration in ~140 lines.
3. [`tests/smoke.sh`](../tests/smoke.sh) — the entire test surface.

If you have 15 minutes, additionally read [`cpu_thermals/backends/README.md`](../cpu_thermals/backends/README.md) and [`cpu_thermals/output/README.md`](../cpu_thermals/output/README.md).

## What is *out of scope* (do not propose without checking with the user first)

- New runtime dependencies.
- A test framework (pytest, unittest, etc.).
- Linting/formatting CI gates (ruff, mypy, black, pre-commit). Not opposed in principle; just orthogonal to "does the code work".
- Wide-format CSV. The long format is load-bearing for cross-machine consolidation.
- A web UI / Prometheus exporter / Datadog integration. The on-disk CSV is the integration point; downstream tools subscribe to that.
- Windows support. cpu_thermals is Linux + macOS Apple Silicon by design.
