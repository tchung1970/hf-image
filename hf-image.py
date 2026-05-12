#!/usr/bin/env python3
"""Interactive Higgsfield image generator.

Flow: pick model → pick aspect ratio → enter prompt → generate.

Requires `higgsfield` CLI on PATH and a prior `higgsfield auth login`.
"""
import itertools
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_RED = "\033[31m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"

# Models shown in the picker. `fixed` are params we don't ask about.
# `default_credits` is the cost at the default params shown in `display`.
MODELS = [
    {
        "id": "gpt_image_2",
        "display": "GPT Image 2 (Medium, 2K)",
        "fixed": {"quality": "medium", "resolution": "2k"},
        "default_credits": 3,
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
        "default_aspect": "16:9",
    },
    {
        "id": "nano_banana_flash",
        "display": "Nano Banana 2 (2K)",
        "fixed": {"resolution": "2k"},
        "default_credits": 2,
        "aspect_ratios": ["1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "9:16", "16:9", "21:9"],
        "default_aspect": "16:9",
    },
    {
        "id": "nano_banana_2",
        "display": "Nano Banana Pro (2K)",
        "fixed": {"resolution": "2k"},
        "default_credits": 2,
        "aspect_ratios": ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "9:16", "16:9", "21:9"],
        "default_aspect": "16:9",
    },
    {
        "id": "flux_2",
        "display": "FLUX.2 Pro (2K)",
        "fixed": {"model": "pro", "resolution": "2k"},
        "default_credits": 1.5,
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16"],
        "default_aspect": "16:9",
    },
    {
        "id": "seedream_v5_lite",
        "display": "Seedream 5.0 Lite (2K)",
        "fixed": {},
        "default_credits": 1,
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16"],
        "default_aspect": "16:9",
    },
    {
        "id": "z_image",
        "display": "Z-Image (2K)",
        "fixed": {},
        "default_credits": 0.15,
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16"],
        "default_aspect": "16:9",
    },
]
DEFAULT_MODEL_INDEX = 5  # Z-Image


def _ar_sort_key(ar: str) -> tuple[int, int]:
    """Sort aspect ratios numerically by (left, right), 'auto' first."""
    if ar == "auto":
        return (-1, -1)
    a, b = ar.split(":")
    return (int(a), int(b))


for _m in MODELS:
    _m["aspect_ratios"] = sorted(_m["aspect_ratios"], key=_ar_sort_key)


DEFAULT_PROMPT = (
    "A majestic whale swimming in a deep blue sea, sunlight filtering through "
    "the water, gentle waves above, cinematic lighting, realistic ocean "
    "atmosphere, peaceful mood, high detail."
)
DOWNLOAD_DIR = Path.cwd()


def _credit_str(credits) -> str:
    """'1 credit', '1.5 credits', '3 credits', or 'unknown'."""
    if credits is None:
        return "unknown"
    return f"{credits:g} credit{'' if credits == 1 else 's'}"


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds like '43s' or '1m 23s'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    return f"{m}m {s:02d}s"


def _quit_if(raw: str) -> None:
    if raw.lower() in ("q", "quit", "exit"):
        print("Bye.")
        sys.exit(0)


def pick(label: str, options: list[str], default: str | None) -> str:
    default_idx = options.index(default) if default in options else 0
    print(f"\n{label}:")
    for i, opt in enumerate(options, start=1):
        marker = " (default)" if i - 1 == default_idx else ""
        print(f"  {i}. {opt}{marker}")
    raw = input(f"Choose [1-{len(options)}, Enter for default, q to quit]: ").strip()
    _quit_if(raw)
    if not raw:
        return options[default_idx]
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass
    sys.stderr.write(f"Invalid choice: {raw}\n")
    sys.exit(2)


def pick_model() -> dict:
    print("\nAvailable models:")
    width = max(len(m["display"]) for m in MODELS)
    for i, m in enumerate(MODELS, start=1):
        marker = " (default)" if i - 1 == DEFAULT_MODEL_INDEX else ""
        print(f"  {i}. {m['display']:<{width}}  {_credit_str(m['default_credits'])}{marker}")
    raw = input(f"Choose model [1-{len(MODELS)}, Enter for default, q to quit]: ").strip()
    _quit_if(raw)
    if not raw:
        return MODELS[DEFAULT_MODEL_INDEX]
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(MODELS):
            return MODELS[idx]
    except ValueError:
        pass
    sys.stderr.write(f"Invalid choice: {raw}\n")
    sys.exit(2)


def get_cost(model_id: str, params: dict) -> float | None:
    """Return the exact credit cost (may be fractional)."""
    cmd = ["higgsfield", "generate", "cost", model_id, "--prompt", "x", "--json"]
    for k, v in params.items():
        cmd += [f"--{k}", str(v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
        # Prefer credits_exact (may be fractional, e.g. 1.5); fall back to credits.
        val = data.get("credits_exact", data.get("credits"))
        return float(val) if val is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def main() -> int:
    model = pick_model()
    params: dict = dict(model["fixed"])
    params["aspect_ratio"] = pick(
        f"Aspect ratios for {model['display']}",
        model["aspect_ratios"],
        model["default_aspect"],
    )

    cost = get_cost(model["id"], params)
    cost_str = _credit_str(cost)
    print(f"\nEstimated cost: {cost_str}")

    print(f"\nDefault prompt:\n  {DEFAULT_PROMPT}")
    raw = input("\nEnter your prompt (Enter for default, q to quit): ").strip()
    _quit_if(raw)
    prompt = raw or DEFAULT_PROMPT

    confirm = input(f"\nGenerate with {model['display']} for {cost_str}? [Y/n]: ").strip().lower()
    _quit_if(confirm)
    if confirm and confirm not in ("y", "yes"):
        print("Cancelled.")
        return 0

    summary = f"{model['display']} | " + " | ".join(f"{k}={v}" for k, v in params.items())
    print(f"\n→ {summary} | {cost_str}")

    # Step 1: submit the job (silent, capture JSON to get the job id).
    create_cmd = [
        "higgsfield", "generate", "create", model["id"],
        "--prompt", prompt, "--json",
    ]
    for k, v in params.items():
        create_cmd += [f"--{k}", str(v)]
    print("Submitting...")
    submit = subprocess.run(create_cmd, capture_output=True, text=True)
    if submit.returncode != 0:
        sys.stderr.write(submit.stderr or submit.stdout)
        return submit.returncode
    job_ids = _extract_ids(json.loads(submit.stdout))
    if not job_ids:
        sys.stderr.write("No job id in CLI response:\n" + submit.stdout)
        return 1

    # Step 2: poll each job with a fancy spinner + elapsed counter.
    urls: list[str] = []
    for jid in job_ids:
        job = _wait_with_progress(jid)
        if job.get("status") != "completed":
            sys.stderr.write(f"Job {jid} ended with status: {job.get('status')}\n")
            return 1
        urls.extend(_extract_urls(job))
    if not urls:
        sys.stderr.write("No result URLs after wait.\n")
        return 1

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, url in enumerate(urls, start=1):
        suffix = Path(url.split("?")[0]).suffix or ".png"
        base = f"hf_{model['id']}_{stamp}"
        name = f"{base}{suffix}" if len(urls) == 1 else f"{base}_{i}{suffix}"
        dest = DOWNLOAD_DIR / name
        urllib.request.urlretrieve(url, dest)
        print(f"✓ {dest}")
        subprocess.run(["open", str(dest)])
    return 0


def _wait_with_progress(job_id: str, poll_interval: float = 2.0) -> dict:
    """Poll a job until terminal status, rendering a spinner + elapsed counter.

    Returns the final job dict.
    """
    start = time.time()
    spinner = itertools.cycle(SPINNER_FRAMES)
    job: dict = {}
    status = "pending"
    last_poll = 0.0
    use_color = sys.stdout.isatty()
    cy = C_CYAN if use_color else ""
    dm = C_DIM if use_color else ""
    rs = C_RESET if use_color else ""

    while True:
        now = time.time()
        elapsed = now - start
        if last_poll == 0.0 or (now - last_poll) >= poll_interval:
            r = subprocess.run(
                ["higgsfield", "generate", "get", job_id, "--json"],
                capture_output=True, text=True,
            )
            last_poll = now
            if r.returncode == 0:
                try:
                    p = json.loads(r.stdout)
                    job = p[0] if isinstance(p, list) and p else (p if isinstance(p, dict) else {})
                    status = job.get("status", status)
                except (json.JSONDecodeError, IndexError, TypeError):
                    pass

        sys.stdout.write(
            f"\r  {cy}{next(spinner)}{rs} {status:<12} {dm}[{_fmt_elapsed(elapsed)}]{rs}    "
        )
        sys.stdout.flush()
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.1)

    final_color = (C_GREEN if status == "completed" else C_RED) if use_color else ""
    mark = "✓" if status == "completed" else "✗"
    sys.stdout.write(
        f"\r  {final_color}{mark}{rs} {status:<12} {dm}[{_fmt_elapsed(elapsed)}]{rs}    \n"
    )
    sys.stdout.flush()
    return job


def _extract_ids(payload) -> list[str]:
    """Pull job IDs out of `higgsfield generate create --json` output.

    The CLI returns either a list of UUID strings or a list of dicts with an `id` key.
    """
    if isinstance(payload, list):
        out = []
        for item in payload:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and item.get("id"):
                out.append(item["id"])
        return out
    if isinstance(payload, dict) and payload.get("id"):
        return [payload["id"]]
    if isinstance(payload, str):
        return [payload]
    return []


def _extract_urls(payload) -> list[str]:
    urls: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("result_url", "rawUrl", "url") and isinstance(v, str) and v.startswith("http"):
                    urls.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("\nAvailable models:")
        width = max(len(m["display"]) for m in MODELS)
        for i, m in enumerate(MODELS, start=1):
            mark = " (default)" if i - 1 == DEFAULT_MODEL_INDEX else ""
            print(f"  {i}. {m['display']:<{width}}  {_credit_str(m['default_credits'])}{mark}")
        print(f"\nOutput: {DOWNLOAD_DIR}/ (auto-opens)")
        sys.exit(0)
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
        sys.exit(0)
