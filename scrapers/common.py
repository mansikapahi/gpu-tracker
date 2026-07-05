"""Shared schema and helpers for all provider scrapers.

Every scraper returns a list of Offer dicts. run_all.py merges them,
stamps metadata, and writes site/data/gpus.json for the frontend.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "site" / "data" / "gpus.json"

# Canonical GPU model names. Scrapers map provider-specific labels onto these
# so the frontend can group and compare across providers.
CANONICAL_MODELS = {
    r"h200": "H200",
    r"h100[\s-]*(sxm|hbm3)?": "H100 SXM",
    r"h100[\s-]*(pcie|pcie5)": "H100 PCIe",
    r"a100[\s-]*(sxm)?[\s-]*80": "A100 80GB",
    r"a100[\s-]*40": "A100 40GB",
    r"l40s": "L40S",
    r"a6000": "RTX A6000",
    r"6000\s*ada": "RTX 6000 Ada",
    r"4090": "RTX 4090",
    r"5090": "RTX 5090",
    r"b200": "B200",
}


def canonical_model(raw: str) -> str | None:
    """Map a provider label like 'NVIDIA H100 80GB SXM5' to a canonical name.

    Returns None for models we don't track (keeps the dataset focused).
    """
    label = raw.lower()
    for pattern, name in CANONICAL_MODELS.items():
        if re.search(pattern, label):
            return name
    return None


@dataclass
class Offer:
    provider: str            # display name, e.g. "RunPod"
    provider_slug: str       # stable id, e.g. "runpod"
    gpu_model: str           # canonical name from canonical_model()
    vram_gb: int
    price_hour_usd: float    # on-demand price per GPU per hour
    gpu_count: int = 1       # offers are normalised to per-GPU price
    kind: str = "on-demand"  # "on-demand" | "spot" | "community"
    region: str | None = None
    source_url: str = ""     # page the price came from (also used for citations)
    affiliate_url: str | None = None  # referral link if you have one
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def as_dict(self) -> dict:
        return asdict(self)


HISTORY_PATH = Path(__file__).resolve().parent.parent / "site" / "data" / "history.json"
HISTORY_MAX_DAYS = 730


def update_history(offers: list[Offer], today: str | None = None) -> None:
    """Append today's floor price per (provider, model) to history.json.

    Shape: {"days": {"2026-07-05": {"runpod|H100 SXM": 2.69, ...}, ...}}
    One entry per day; re-runs on the same day overwrite (keeps the file small
    and the series clean). Capped at HISTORY_MAX_DAYS.
    """
    today = today or datetime.now(timezone.utc).date().isoformat()
    history = {"days": {}}
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text())

    floors: dict[str, float] = {}
    for o in offers:
        key = f"{o.provider_slug}|{o.gpu_model}"
        if key not in floors or o.price_hour_usd < floors[key]:
            floors[key] = round(o.price_hour_usd, 3)
    history["days"][today] = floors

    # trim to the newest HISTORY_MAX_DAYS entries
    keep = sorted(history["days"])[-HISTORY_MAX_DAYS:]
    history["days"] = {d: history["days"][d] for d in keep}

    HISTORY_PATH.write_text(json.dumps(history, separators=(",", ":")))
    print(f"History: {len(history['days'])} days in {HISTORY_PATH.name}")


def write_output(offers: list[Offer], errors: dict[str, str]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offer_count": len(offers),
        "errors": errors,  # provider_slug -> error message; frontend shows staleness
        "offers": [o.as_dict() for o in offers],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(offers)} offers to {OUTPUT_PATH}")
