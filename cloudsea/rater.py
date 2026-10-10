"""Gemma rates a summit photo: evidence questions first, then the label (Phase 0: 7-8/11 vs 3/11 label-first).

The uploader confirms or corrects the label with one tap; only confirmed labels count as ground truth.
"""
from __future__ import annotations

import base64
import json

from cloudsea import gemma

LABELS = ["cloud_sea", "partial", "clear_no_sea", "socked_in", "unusable"]
CONFIRMABLE = LABELS[:4]

PROMPT = """This photo was taken around sunrise from the summit of Nandi Hills near Bangalore.
Answer each question about what is actually visible, then give your overall label.
- nearby_objects_hazy: are trees, railings, rocks or people close to the camera softened or greyed by fog?
- ground_visible_far_below: can you see distant land, fields, roads or towns far below the viewpoint?
- layer_below_horizon: is there a white or grey layer of cloud or fog spread out BELOW the viewer, with its upper surface visible?
- evidence: one sentence naming what you see.
- label: cloud_sea (layer below with its top visible, little ground), partial (layer below but much ground visible),
  clear_no_sea (ground visible, no layer below), socked_in (inside fog, no distant view), unusable (not a hilltop view).
- confidence: from 0 to 1."""

SCHEMA = {
    "type": "object",
    "properties": {
        "nearby_objects_hazy": {"type": "boolean"},
        "ground_visible_far_below": {"type": "boolean"},
        "layer_below_horizon": {"type": "boolean"},
        "evidence": {"type": "string"},
        "label": {"type": "string", "enum": LABELS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["nearby_objects_hazy", "ground_visible_far_below", "layer_below_horizon",
                 "evidence", "label", "confidence"],
}


def rate_photo(jpeg: bytes) -> dict:
    """Return {"label", "confidence", "evidence", "answers": {...}}. Raises on transport errors or bad JSON."""
    resp = gemma.chat([{"role": "user", "content": PROMPT, "images": [base64.b64encode(jpeg).decode()]}],
                      format=SCHEMA, options={"temperature": 0})
    out = json.loads(resp["message"]["content"])
    if out.get("label") not in LABELS:
        raise ValueError(f"unexpected label {out.get('label')!r}")
    return {
        "label": out["label"],
        "confidence": max(0.0, min(1.0, float(out.get("confidence", 0)))),
        "evidence": str(out.get("evidence", ""))[:300],
        "answers": {k: bool(out.get(k)) for k in
                    ("nearby_objects_hazy", "ground_visible_far_below", "layer_below_horizon")},
    }
