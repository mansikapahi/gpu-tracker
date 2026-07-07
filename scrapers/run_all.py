"""Run all provider scrapers and write site/data/gpus.json.

Usage:
    python run_all.py            # live scrape (needs network)
    python run_all.py --sample   # write realistic sample data for development

One failing provider never kills the run: its error is recorded in the output
so the frontend can show "provider data may be stale".
"""
from __future__ import annotations

import sys

from common import Offer, write_output, update_history
from providers import SCRAPERS, backfill_vram, AFFILIATE

# Sample data so you can develop the frontend without network access.
# Prices are illustrative, replace with a live run before publishing anything.
SAMPLE = [
    ("RunPod", "runpod", "B200",      192, 5.98, "on-demand"),
    ("RunPod", "runpod", "H200",      141, 3.59, "on-demand"),
    ("RunPod", "runpod", "H100 SXM",   80, 2.69, "on-demand"),
    ("RunPod", "runpod", "H100 SXM",   80, 1.99, "community"),
    ("RunPod", "runpod", "A100 80GB",  80, 1.64, "on-demand"),
    ("RunPod", "runpod", "L40S",       48, 0.86, "on-demand"),
    ("RunPod", "runpod", "RTX 4090",   24, 0.69, "on-demand"),
    ("RunPod", "runpod", "RTX 4090",   24, 0.34, "community"),
    ("Vast.ai", "vastai", "H200",     141, 2.95, "on-demand"),
    ("Vast.ai", "vastai", "H100 SXM",  80, 1.87, "on-demand"),
    ("Vast.ai", "vastai", "A100 80GB", 80, 1.09, "on-demand"),
    ("Vast.ai", "vastai", "RTX 5090",  32, 0.61, "on-demand"),
    ("Vast.ai", "vastai", "RTX 4090",  24, 0.29, "on-demand"),
    ("Lambda", "lambda", "B200",      192, 4.99, "on-demand"),
    ("Lambda", "lambda", "H100 SXM",   80, 2.99, "on-demand"),
    ("Lambda", "lambda", "A100 40GB",  40, 1.29, "on-demand"),
]

SOURCE_URLS = {
    "runpod": "https://www.runpod.io/pricing",
    "vastai": "https://vast.ai/pricing",
    "lambda": "https://lambda.ai/service/gpu-cloud",
}


def sample_offers() -> list[Offer]:
    return [
        Offer(
            provider=p, provider_slug=slug, gpu_model=model, vram_gb=vram,
            price_hour_usd=price, kind=kind,
            source_url=SOURCE_URLS[slug], affiliate_url=AFFILIATE[slug],
        )
        for p, slug, model, vram, price, kind in SAMPLE
    ]


def sample_history(offers: list[Offer], days: int = 90) -> None:
    """Synthetic 90-day history so the frontend has trends to draw in dev."""
    import math
    import random
    from datetime import date, timedelta

    random.seed(7)
    drift = {o.provider_slug + "|" + o.gpu_model: random.uniform(1.05, 1.35)
             for o in offers}  # prices trended down toward today's value
    for i in range(days, -1, -1):
        day = (date.today() - timedelta(days=i)).isoformat()
        snapshot = []
        for o in offers:
            key = o.provider_slug + "|" + o.gpu_model
            factor = 1 + (drift[key] - 1) * (i / days)          # linear decay
            wobble = 1 + 0.04 * math.sin(i / 6 + hash(key) % 10)  # noise
            snapshot.append(Offer(**{**o.as_dict(),
                                     "price_hour_usd": round(o.price_hour_usd * factor * wobble, 3)}))
        update_history(snapshot, today=day)




def sanity_filter(offers: list[Offer]) -> list[Offer]:
    """Drop implausibly cheap offers (glitched marketplace listings).

    Rule: within each GPU model, any offer priced below 35% of the model's
    cheapest ON-DEMAND price is considered a data glitch and dropped.
    Community/spot offers are legitimately cheaper, but a 141GB H200 at
    $0.50/hr next to a $2.29 on-demand floor is a broken listing, not a deal.
    Models with no on-demand reference are left untouched.
    """
    floor_od: dict[str, float] = {}
    for o in offers:
        if o.kind == "on-demand":
            if o.gpu_model not in floor_od or o.price_hour_usd < floor_od[o.gpu_model]:
                floor_od[o.gpu_model] = o.price_hour_usd

    kept: list[Offer] = []
    for o in offers:
        ref = floor_od.get(o.gpu_model)
        if ref and o.price_hour_usd < 0.35 * ref:
            print(f"[sanity] dropped {o.provider} {o.gpu_model} "
                  f"${o.price_hour_usd}/hr (< 35% of ${ref} on-demand floor)")
            continue
        kept.append(o)
    return kept


def main() -> int:
    if "--sample" in sys.argv:
        offers = sample_offers()
        write_output(offers, errors={})
        sample_history(offers)
        return 0

    offers: list[Offer] = []
    errors: dict[str, str] = {}
    for slug, fn in SCRAPERS.items():
        try:
            got = fn()
            print(f"[{slug}] {len(got)} offers")
            offers.extend(got)
        except Exception as exc:  # noqa: BLE001 - isolate provider failures
            print(f"[{slug}] FAILED: {exc}", file=sys.stderr)
            errors[slug] = str(exc)

    if not offers:
        print("All providers failed; keeping previous data file.", file=sys.stderr)
        return 1

    offers = sanity_filter(backfill_vram(offers))
    write_output(offers, errors)
    update_history(offers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
