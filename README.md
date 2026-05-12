# hf-image.py

Interactive Higgsfield image generator. Wraps the `higgsfield` CLI in a small
Python script with a model picker, aspect-ratio picker, default prompt, and a
fancy progress bar.

## Requirements

### Runtime

- **macOS.** The script calls `open <file>` to auto-launch the result in
  Preview. Everything else is portable — on Linux, replace `open` with
  `xdg-open`; on Windows, with `start`. See `subprocess.run(["open", ...])`
  near the end of `main()` in `hf-image.py`.
- **Python 3.10 or newer.** Uses PEP 604 union syntax (`str | None`,
  `float | None`) in type hints. No virtualenv needed — the script is
  stdlib-only (`subprocess`, `urllib.request`, `json`, `itertools`, `time`,
  `datetime`, `pathlib`, `sys`). No `pip install` step.
- **Terminal with UTF-8 + ANSI escape support.** The progress bar uses Braille
  spinner characters (`⠋⠙⠹…`) and ANSI color codes. Colors auto-disable when
  stdout is not a TTY (e.g. piped to a file).
- **Network access** to the Higgsfield API and the CDN that hosts result URLs.
- **Write access to the current working directory.** Output PNGs are saved to
  `cwd` as `hf_<model_id>_YYYYMMDD_HHMMSS.png`.

### Higgsfield CLI

- **Node.js + npm** to install the CLI globally.
- **`@higgsfield/cli` on `PATH`** — installed via
  `npm install -g @higgsfield/cli`. The script shells out to
  `higgsfield generate cost|create|get` and parses `--json` output.
- **A logged-in Higgsfield account with credits.** Run `higgsfield auth login`
  once (opens a browser); confirm with `higgsfield account status`. Every
  `generate create` call burns credits from your account balance — the script
  has no free/Unlimited path (see [Known limitations](#known-limitations)).

## Setup

Install the Higgsfield CLI (requires Node.js) and authenticate:

```bash
npm install -g @higgsfield/cli
higgsfield auth login   # opens a browser
```

Verify:

```bash
higgsfield account status
```

## Install

Optional — symlink the script into a directory on your `PATH` so you can run
`hf-image` from anywhere:

```bash
ln -s "$PWD/hf-image.py" ~/bin/hf-image
```

(Assumes `~/bin` is on your `PATH`. Adjust the target to wherever you keep
user scripts, e.g. `/usr/local/bin`.)

## Usage

```bash
./hf-image.py
```

Or, if symlinked onto `PATH` (see [Install](#install)):

```bash
hf-image
```

Then follow the prompts:

1. **Pick a model** (Enter for the default — Z-Image, 0.15 credits).
2. **Pick an aspect ratio** (Enter for 16:9).
3. **Enter a prompt** (Enter to use the built-in default, shown below).
4. **Confirm** (`Y` to generate, `n` to cancel).

Built-in default prompt:

> A majestic whale swimming in a deep blue sea, sunlight filtering through the
> water, gentle waves above, cinematic lighting, realistic ocean atmosphere,
> peaceful mood, high detail.

`q` quits at any picker or prompt. `Ctrl-C` / `Ctrl-D` also exit cleanly.

Output is saved to the current working directory as
`hf_<model_id>_YYYYMMDD_HHMMSS.png` and auto-opened in Preview.

## Models

All entries use the model's web-UI-default settings. Costs are for a single
generation at the listed params.

| # | Model                       | Fixed params                              | Credits |
|---|-----------------------------|-------------------------------------------|---------|
| 1 | GPT Image 2 (Medium, 2K)    | `quality=medium`, `resolution=2k`         | 3       |
| 2 | Nano Banana 2 (2K)          | `resolution=2k`                           | 2       |
| 3 | Nano Banana Pro (2K)        | `resolution=2k`                           | 2       |
| 4 | FLUX.2 Pro (2K)             | `model=pro`, `resolution=2k`              | 1.5     |
| 5 | Seedream 5.0 Lite (2K)      | _(none — model has no `resolution` flag)_ | 1       |
| 6 | Z-Image (2K)                | _(none — model has no `resolution` flag)_ | 0.15    |

The picker queries `higgsfield generate cost` after the aspect-ratio step to
show the exact cost (including fractional values) before you commit.

## Flow internals

1. `higgsfield generate cost ... --json` → preview credits (free).
2. `higgsfield generate create ... --json` → submit, returns job UUID.
3. Poll `higgsfield generate get <id> --json` every 2 s, rendering a spinner +
   live elapsed counter (`[Xs]` or `[Xm Ys]`).
4. Download the `result_url` to the cwd and `open` it.

## Known limitations

These are public-API limitations, not script bugs. They apply to the raw REST
API equally — the CLI is a thin client.

- **No "Unlimited" toggle.** The web UI's Unlimited switch (free generations on
  certain plans) is not exposed via the CLI/API. Every CLI call burns credits.
- **Seedream 5.0 Lite has no `resolution` param.** The UI offers 2K/3K/4K under
  "Select quality", but only `quality=basic|high` is accepted by the CLI, and
  output is fixed at the model's native ~2848×1600.
- **Grok Imagine has no `resolution` param.** Renders at 1408×768 (1K) only.
  (Removed from this script's picker for that reason.)
- **Z-Image has no `resolution` or `quality` param.** The CLI accepts only
  `prompt` and `aspect_ratio`; output is at the model's native resolution.
- **GPT Image 2 cost varies.** `quality × resolution` matrix:
  - low × any → 1
  - medium × 1k/2k/4k → 2/3/6
  - high × 1k/2k/4k → 4/7/12
  - This script uses `medium + 2k` (3 credits) to match the web UI default.

## Customizing

Edit `MODELS` in `hf-image.py` to add/remove entries or change fixed params and
default credits. Each entry needs:

```python
{
    "id": "<job_set_type from `higgsfield model list`>",
    "display": "<label shown in the picker>",
    "fixed": {"<param>": "<value>", ...},
    "default_credits": <int or float>,
    "aspect_ratios": ["1:1", "16:9", ...],
    "default_aspect": "16:9",
}
```

The script sorts aspect ratios numerically by `(a, b)` for consistent display
(`auto` floats to the top when present).

Edit `DEFAULT_PROMPT` for the built-in fallback prompt; edit
`DEFAULT_MODEL_INDEX` to change which model is pre-selected.
