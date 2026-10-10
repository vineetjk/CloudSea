"""Phase 0 benchmark: Gemma 4 on Ollama. Text speed, tool-calling reliability, photo-rating latency, memory.

Runs against whatever Ollama $OLLAMA_URL points at, so the same script benchmarks the Mac and Render.
Tool results here are fixed benchmark fixtures, not forecasts.
"""
from __future__ import annotations

import argparse
import base64
import json
import platform
import re
import statistics
import subprocess
import time
from pathlib import Path

import httpx

from cloudsea import settings

PHOTO_LABELS = ["cloud_sea", "partial", "clear_no_sea", "socked_in", "unusable"]

# v2 (evidence first). v1 put the label first and E2B answered cloud_sea for almost everything (3/11 agreement);
# asking what is visible before the label raised agreement to 8/11. Thinking mode made it worse and 5x slower.
RATING_PROMPT = """This photo was taken around sunrise from the summit of Nandi Hills near Bangalore.
Answer each question about what is actually visible, then give your overall label.
- nearby_objects_hazy: are trees, railings, rocks or people close to the camera softened or greyed by fog?
- ground_visible_far_below: can you see distant land, fields, roads or towns far below the viewpoint?
- layer_below_horizon: is there a white or grey layer of cloud or fog spread out BELOW the viewer, with its upper surface visible?
- evidence: one sentence naming what you see.
- label: cloud_sea (layer below with its top visible, little ground), partial (layer below but much ground visible),
  clear_no_sea (ground visible, no layer below), socked_in (inside fog, no distant view), unusable (not a hilltop view).
- confidence: from 0 to 1."""

RATING_SCHEMA = {
    "type": "object",
    "properties": {
        "nearby_objects_hazy": {"type": "boolean"},
        "ground_visible_far_below": {"type": "boolean"},
        "layer_below_horizon": {"type": "boolean"},
        "evidence": {"type": "string"},
        "label": {"type": "string", "enum": PHOTO_LABELS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["nearby_objects_hazy", "ground_visible_far_below", "layer_below_horizon",
                 "evidence", "label", "confidence"],
}

# v2. v1 said "call every tool you need" and E2B called only get_leave_by (0/5 fully OK).
# Naming the four tools fixed it (5/5, all four called in one round); the harness also re-asks for any skipped tool.
WRITER_SYSTEM = """You write tomorrow's sunrise call for Nandi Hills for people deciding tonight whether to set an alarm.
Before writing, call all four tools: get_forecast, get_sunrise, get_leave_by (with the user's area) and get_conditions.
Then write at most 45 words in a calm, plain tone: the call and probability, sunrise time, leave-by time, and one line on what to carry.
Use only numbers that appear in tool results. Never urge anyone to hurry or drive fast. Say it is a forecast, not a guarantee."""
MAX_NUDGES = 3

TOOLS = [
    {"type": "function", "function": {
        "name": "get_forecast", "description": "Tomorrow's cloud-sea probability and the GO/MAYBE/SKIP call.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_sunrise", "description": "Sunrise and first-light times at the Nandi Hills summit tomorrow.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_leave_by", "description": "Latest safe departure time from an area, including a safety buffer.",
        "parameters": {"type": "object", "properties": {"area": {"type": "string"}}, "required": ["area"]}}},
    {"type": "function", "function": {
        "name": "get_conditions", "description": "Expected summit temperature, wind and recent rain.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

FIXTURES = {
    "get_forecast": {"date": "Sun 11 Oct", "cloud_sea_probability_pct": 34, "call": "MAYBE"},
    "get_sunrise": {"sunrise": "06:09", "first_light": "05:47"},
    "get_leave_by": {"area": "Electronics City", "drive_minutes": 105, "buffer_minutes": 20, "leave_by": "03:34"},
    "get_conditions": {"summit_temp_c": 15, "wind_kmh": 6, "rain_last_24h_mm": 0},
}

TEXT_PROMPT = ("In about 150 words, explain to a first-time visitor why fog forms in the valleys around "
               "Nandi Hills on calm winter nights.")


def chat(http: httpx.Client, **body) -> dict:
    body.setdefault("model", settings.GEMMA_MODEL)
    body.setdefault("stream", False)
    body.setdefault("think", False)
    r = http.post("/api/chat", json=body)
    r.raise_for_status()
    return r.json()


def rates(resp: dict) -> dict:
    ns = 1e9
    return {
        "load_s": round(resp.get("load_duration", 0) / ns, 2),
        "prompt_tokens": resp.get("prompt_eval_count", 0),
        "prompt_tok_s": round(resp.get("prompt_eval_count", 0) / max(resp.get("prompt_eval_duration", 1) / ns, 1e-9), 1),
        "gen_tokens": resp.get("eval_count", 0),
        "gen_tok_s": round(resp.get("eval_count", 0) / max(resp.get("eval_duration", 1) / ns, 1e-9), 1),
        "total_s": round(resp.get("total_duration", 0) / ns, 2),
    }


def mac_memory() -> dict:
    """Resident memory of Ollama processes and system swap (macOS only; Render reports via /api/ps)."""
    if platform.system() != "Darwin":
        return {}
    ps = subprocess.run(["ps", "-axo", "rss=,comm="], capture_output=True, text=True, check=False).stdout
    rss_kb = sum(int(line.split()[0]) for line in ps.splitlines() if "ollama" in line.lower())
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True,
                          check=False).stdout.strip()
    return {"ollama_rss_gb": round(rss_kb / 1024 / 1024, 2), "swap": swap}


def bench_text(http: httpx.Client, runs: int) -> dict:
    http.post("/api/generate", json={"model": settings.GEMMA_MODEL, "keep_alive": 0})  # unload: first run is cold
    results = []
    for _ in range(runs):
        resp = chat(http, messages=[{"role": "user", "content": TEXT_PROMPT}],
                    options={"num_predict": 200, "temperature": 0.7})
        results.append(rates(resp))
    warm = results[1:] or results
    return {"cold": results[0], "warm_gen_tok_s_median": statistics.median(r["gen_tok_s"] for r in warm),
            "warm_prompt_tok_s_median": statistics.median(r["prompt_tok_s"] for r in warm), "runs": results}


NUM_RE = re.compile(r"\d+(?::\d+)?")


def allowed_numbers() -> set[str]:
    nums: set[str] = set()
    for fixture in FIXTURES.values():
        for v in fixture.values():
            nums.update(NUM_RE.findall(str(v)))
    return nums


def bench_tools(http: httpx.Client, trials: int) -> dict:
    allowed = allowed_numbers()
    out = []
    for _ in range(trials):
        messages = [{"role": "system", "content": WRITER_SYSTEM},
                    {"role": "user", "content": "Area: Electronics City. Write tomorrow's call."}]
        called, nudges, t0, text = [], 0, time.perf_counter(), ""
        for _round in range(8):
            msg = chat(http, messages=messages, tools=TOOLS, options={"temperature": 0.3})["message"]
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            for call in calls:
                name = call["function"]["name"]
                called.append(name)
                messages.append({"role": "tool", "tool_name": name,
                                 "content": json.dumps(FIXTURES.get(name, {"error": "unknown tool"}))})
            if calls:
                continue
            missing = set(FIXTURES) - set(called)
            if missing and nudges < MAX_NUDGES:
                nudges += 1
                messages.append({"role": "user", "content": f"Before writing, call: {', '.join(sorted(missing))}."})
                continue
            text = msg.get("content", "").strip()
            break
        found = NUM_RE.findall(text)
        bad = [n for n in found if n not in allowed]
        out.append({
            "seconds": round(time.perf_counter() - t0, 1), "tools_called": called, "nudges": nudges,
            "all_four_tools": set(FIXTURES) <= set(called), "words": len(text.split()),
            "numbers_ok": not bad, "unsupported_numbers": bad, "text": text,
        })
    ok = [t for t in out if t["all_four_tools"] and t["numbers_ok"] and 0 < t["words"] <= 45]
    return {"trials": trials, "fully_ok": len(ok),
            "median_seconds": statistics.median(t["seconds"] for t in out), "results": out}


def bench_photos(http: httpx.Client, photo_dir: Path, labels: dict) -> dict:
    out = []
    for path in sorted(photo_dir.glob("*.jpg")):
        img = base64.b64encode(path.read_bytes()).decode()
        t0 = time.perf_counter()
        resp = chat(http, messages=[{"role": "user", "content": RATING_PROMPT, "images": [img]}],
                    format=RATING_SCHEMA, options={"temperature": 0})
        wall = time.perf_counter() - t0
        try:
            rating = json.loads(resp["message"]["content"])
            valid = rating.get("label") in PHOTO_LABELS and 0 <= float(rating.get("confidence", -1)) <= 1
        except (json.JSONDecodeError, TypeError, ValueError):
            rating, valid = {"raw": resp["message"]["content"]}, False
        ref = labels.get(path.name, "uncertain")
        out.append({"photo": path.name, "kb": path.stat().st_size // 1024, "seconds": round(wall, 1),
                    "valid_json": valid, "reference": ref, "gemma": rating.get("label"),
                    "agrees": None if ref == "uncertain" else rating.get("label") == ref,
                    "confidence": rating.get("confidence"), "evidence": rating.get("evidence"),
                    "answers": {k: rating.get(k) for k in
                                ("nearby_objects_hazy", "ground_visible_far_below", "layer_below_horizon")},
                    **rates(resp)})
    scored = [r for r in out if r["agrees"] is not None]
    return {"photos": len(out), "valid_json": sum(r["valid_json"] for r in out),
            "agreement": f"{sum(r['agrees'] for r in scored)}/{len(scored)}",
            "median_seconds": statistics.median(r["seconds"] for r in out), "results": out}


def wait_for_model(http: httpx.Client, timeout_s: int = 1800) -> None:
    """On a fresh Render disk the service pulls the model after it starts listening."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            names = [m["name"] for m in http.get("/api/tags").json().get("models", [])]
            if settings.GEMMA_MODEL in names:
                print(f"model available after {time.time() - t0:.0f}s", flush=True)
                return
        except httpx.HTTPError:
            pass
        time.sleep(10)
    raise TimeoutError(f"{settings.GEMMA_MODEL} not available at {settings.OLLAMA_URL}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", default=platform.node().split(".")[0], help="name for this machine in the results")
    ap.add_argument("--photos", type=Path, default=Path("data/raw/test_photos"))
    ap.add_argument("--text-runs", type=int, default=4)
    ap.add_argument("--tool-trials", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("docs/phase0"))
    ap.add_argument("--print-json", action="store_true", help="also print the full result to stdout (for Render logs)")
    ap.add_argument("--wait-model", action="store_true", help="wait up to 30 min for Ollama to have the model")
    args = ap.parse_args()

    labels = json.loads((Path(__file__).parent / "test_photo_labels.json").read_text())
    with httpx.Client(base_url=settings.OLLAMA_URL, timeout=900) as http:
        if args.wait_model:
            wait_for_model(http)
        result = {"label": args.label, "model": settings.GEMMA_MODEL,
                  "ollama_version": http.get("/api/version").json().get("version"),
                  "machine": platform.platform(), "memory_before": mac_memory()}
        print("text speed ...", flush=True)
        result["text"] = bench_text(http, args.text_runs)
        result["loaded_models"] = http.get("/api/ps").json().get("models", [])
        result["memory_loaded"] = mac_memory()
        print("tool calling ...", flush=True)
        result["tools"] = bench_tools(http, args.tool_trials)
        print("photo rating ...", flush=True)
        result["photos"] = bench_photos(http, args.photos, labels)
        result["memory_after"] = mac_memory()

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"bench_gemma_{args.label}.json"
    path.write_text(json.dumps(result, indent=2))
    t, tl, ph = result["text"], result["tools"], result["photos"]
    size = next((m.get("size", 0) for m in result["loaded_models"]), 0) / 1e9
    print(f"\n{args.label}: Ollama {result['ollama_version']}, {settings.GEMMA_MODEL}, loaded size {size:.1f} GB")
    print(f"  cold load {t['cold']['load_s']} s | warm generation {t['warm_gen_tok_s_median']} tok/s "
          f"| prompt {t['warm_prompt_tok_s_median']} tok/s")
    print(f"  writer agent: {tl['fully_ok']}/{tl['trials']} fully OK, median {tl['median_seconds']} s")
    print(f"  photo rating: {ph['valid_json']}/{ph['photos']} valid JSON, agreement {ph['agreement']}, "
          f"median {ph['median_seconds']} s/photo")
    print(f"  memory: {result['memory_loaded']}")
    print(f"  saved {path}")
    if args.print_json:
        print("BENCH_JSON " + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
