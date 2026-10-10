"""Gemma writes the call from tool results, and a guardrail checks every number before it is published.

The agent gets four tools (get_forecast, get_sunrise, get_leave_by, get_conditions). Phase 0 showed E2B
calls all four when the prompt names them. The text is then checked:
* every number in it must appear in a tool result (no invented percentages, times or temperatures)
* it must state the verdict, the probability and the leave-by time
* at most 45 words, and none of the hurry words
If a draft fails, Gemma gets another try (up to 3); after that a fixed template is used.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from cloudsea import gemma

MAX_WORDS = 45
MAX_ATTEMPTS = 3
BANNED = re.compile(r"\b(hurry|rush|race|racing|speed|fast|quick(ly)?|beat the|don't miss|must go)\b", re.I)
NUM_RE = re.compile(r"\d+(?::\d\d)?")

SYSTEM = """You write tomorrow's sunrise call for Nandi Hills for people deciding tonight whether to set an alarm.
Before writing, call all four tools: get_forecast, get_sunrise, get_leave_by (with the user's area) and get_conditions.
Then write at most 45 words in a calm, plain tone. Start with the call word exactly as get_forecast gives it
(GO, MAYBE or SKIP, in capitals) and its cloud_sea_probability_pct written as a percent, e.g. "SKIP: 8% chance of a cloud sea".
SKIP means a cloud sea is unlikely, GO means it is likely; never change the call.
Then the sunrise time, the leave-by time, and one short line on what to carry.
Copy numbers exactly from tool results and use no other numbers. Never urge anyone to hurry or drive fast."""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_forecast", "description": "Tomorrow's GO/MAYBE/SKIP call and the cloud-sea probability.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_sunrise", "description": "Sunrise and first-light times at the Nandi Hills summit tomorrow.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_leave_by", "description": "Latest departure time from an area, with a safety buffer included.",
        "parameters": {"type": "object", "properties": {"area": {"type": "string"}}, "required": ["area"]}}},
    {"type": "function", "function": {
        "name": "get_conditions", "description": "Expected summit temperature, wind, rain chance and what to carry.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


@dataclass
class Facts:
    """Everything the tools can return. Built by the nightly job from the forecast and the plan."""
    day_label: str            # "Sun 11 Oct"
    verdict: str              # GO | MAYBE | SKIP
    probability_pct: int
    sunrise: str              # "06:09"
    first_light: str
    area_label: str           # "Electronics City"
    drive_minutes: int
    buffer_minutes: int
    leave_by: str             # "03:25"
    summit_temp_c: int | None
    wind_kmh: int | None
    rain_chance_pct: int | None
    carry: list[str]

    def tool(self, name: str) -> dict:
        return {
            "get_forecast": {"date": self.day_label, "call": self.verdict,
                             "cloud_sea_probability_pct": self.probability_pct},
            "get_sunrise": {"sunrise": self.sunrise, "first_light": self.first_light},
            "get_leave_by": {"area": self.area_label, "drive_minutes": self.drive_minutes,
                             "buffer_minutes": self.buffer_minutes, "leave_by": self.leave_by},
            "get_conditions": {"summit_temp_c": self.summit_temp_c, "wind_kmh": self.wind_kmh,
                               "rain_chance_pct": self.rain_chance_pct, "carry": self.carry},
        }.get(name, {"error": f"unknown tool {name}"})

    def allowed_numbers(self) -> set[str]:
        # ensure_ascii=False: an escaped "°" (\u00b0) would otherwise smuggle in "0" and "00" as allowed numbers.
        blob = json.dumps([self.tool(n) for n in ("get_forecast", "get_sunrise", "get_leave_by", "get_conditions")],
                          ensure_ascii=False)
        nums = set(NUM_RE.findall(blob))
        # A leading zero is often dropped in prose ("3:25" for "03:25", "6:09" for "06:09").
        nums |= {n.lstrip("0") for n in nums if ":" in n}
        return nums


def check(text: str, facts: Facts) -> list[str]:
    """Return the problems with a draft; an empty list means it can be published."""
    problems = []
    words = len(text.split())
    if not text.strip():
        return ["empty"]
    if words > MAX_WORDS:
        problems.append(f"{words} words")
    bad = [n for n in NUM_RE.findall(text) if n not in facts.allowed_numbers()]
    if bad:
        problems.append(f"numbers not from tools: {bad}")
    if facts.verdict not in text:
        problems.append("verdict missing")
    if str(facts.probability_pct) not in NUM_RE.findall(text):
        problems.append("probability missing")
    if facts.leave_by not in text and facts.leave_by.lstrip("0") not in text:
        problems.append("leave-by missing")
    if BANNED.search(text):
        problems.append("hurry language")
    return problems


def template(facts: Facts) -> str:
    carry = facts.carry[0][0].lower() + facts.carry[0][1:] if facts.carry else "water"
    return (f"{facts.verdict} for {facts.day_label}: {facts.probability_pct}% chance of a cloud sea at Nandi Hills. "
            f"Sunrise {facts.sunrise}. If you go, leave {facts.area_label} by {facts.leave_by}. Carry a {carry}.")


def _draft(facts: Facts, temperature: float) -> tuple[str, list[str]]:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Area: {facts.area_label}. Write tomorrow's call."}]
    called: list[str] = []
    nudges = 0
    for _ in range(8):
        msg = gemma.chat(messages, tools=TOOLS, options={"temperature": temperature})["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        for c in calls:
            name = c["function"]["name"]
            called.append(name)
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(facts.tool(name), ensure_ascii=False)})
        if calls:
            continue
        missing = {t["function"]["name"] for t in TOOLS} - set(called)
        if missing and nudges < 3:
            nudges += 1
            messages.append({"role": "user", "content": f"Before writing, call: {', '.join(sorted(missing))}."})
            continue
        return msg.get("content", "").strip(), called
    return "", called


def write_call(facts: Facts) -> dict:
    """Return {"text", "source": "gemma"|"template", "attempts": [...]}. Never raises on model trouble."""
    attempts = []
    for i in range(MAX_ATTEMPTS):
        try:
            text, called = _draft(facts, temperature=0.3 + 0.2 * i)
        except Exception as err:  # noqa: BLE001  - any Ollama failure falls through to the template
            attempts.append({"error": repr(err)[:200]})
            break
        problems = check(text, facts)
        attempts.append({"text": text, "tools": called, "problems": problems})
        if not problems:
            return {"text": text, "source": "gemma", "attempts": attempts}
    return {"text": template(facts), "source": "template", "attempts": attempts}
