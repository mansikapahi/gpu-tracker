"""Provider scrapers.

Design rules:
- Each scraper is a function returning list[Offer]; it must raise on failure
  (run_all.py catches per-provider, so one broken provider never kills the run).
- Prefer JSON APIs over HTML scraping; HTML breaks silently and often.
- NOTE: endpoints and response shapes change. Verify each one against the live
  service before first deploy, and check each provider's ToS on automated access.
"""
from __future__ import annotations

import requests

from common import Offer, canonical_model

HEADERS = {"User-Agent": "gpu-price-tracker/0.1 (contact: you@yourdomain.example)"}
TIMEOUT = 30

# Put your referral links here once you're accepted into partner programmes.
AFFILIATE = {
    "runpod": None,   # e.g. "https://runpod.io?ref=XXXX"
    "vastai": None,
    "lambda": None,
}


def scrape_runpod() -> list[Offer]:
    """RunPod exposes GPU types + pricing via its public GraphQL endpoint."""
    query = """
    query GpuTypes {
      gpuTypes {
        id
        displayName
        memoryInGb
        securePrice
        communityPrice
      }
    }
    """
    resp = requests.post(
        "https://api.runpod.io/graphql",
        json={"query": query},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    offers: list[Offer] = []
    for gpu in resp.json()["data"]["gpuTypes"]:
        model = canonical_model(gpu.get("displayName") or "")
        if not model:
            continue
        common_kwargs = dict(
            provider="RunPod",
            provider_slug="runpod",
            gpu_model=model,
            vram_gb=int(gpu.get("memoryInGb") or 0),
            source_url="https://www.runpod.io/pricing",
            affiliate_url=AFFILIATE["runpod"],
        )
        if gpu.get("securePrice"):
            offers.append(Offer(price_hour_usd=float(gpu["securePrice"]),
                                kind="on-demand", **common_kwargs))
        if gpu.get("communityPrice"):
            offers.append(Offer(price_hour_usd=float(gpu["communityPrice"]),
                                kind="community", **common_kwargs))
    return offers


def scrape_vastai() -> list[Offer]:
    """Vast.ai is a marketplace; we take the cheapest verified on-demand offer
    per GPU model as the headline price."""
    resp = requests.post(
        "https://console.vast.ai/api/v0/bundles/",
        json={
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "type": "on-demand",
            "limit": 512,
        },
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    cheapest: dict[str, dict] = {}
    for o in resp.json().get("offers", []):
        model = canonical_model(o.get("gpu_name") or "")
        num = int(o.get("num_gpus") or 1)
        if not model or num < 1:
            continue
        per_gpu = float(o.get("dph_total") or 0) / num
        if per_gpu <= 0:
            continue
        if model not in cheapest or per_gpu < cheapest[model]["price"]:
            cheapest[model] = {
                "price": per_gpu,
                "vram": int((o.get("gpu_ram") or 0) / 1024) or 0,
                "region": o.get("geolocation"),
            }
    return [
        Offer(
            provider="Vast.ai",
            provider_slug="vastai",
            gpu_model=model,
            vram_gb=d["vram"],
            price_hour_usd=round(d["price"], 3),
            kind="on-demand",
            region=d["region"],
            source_url="https://vast.ai/pricing",
            affiliate_url=AFFILIATE["vastai"],
        )
        for model, d in cheapest.items()
    ]


def scrape_lambda() -> list[Offer]:
    """Lambda's instance-types API needs an account key, so v1 parses the
    public pricing page. Fragile by nature - the frontend shows per-provider
    staleness so a silent break is still visible."""
    from html.parser import HTMLParser
    import re

    resp = requests.get("https://lambda.ai/service/gpu-cloud",
                        headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    text = re.sub(r"<[^>]+>", " ", resp.text)

    offers: list[Offer] = []
    # Matches e.g. "8x NVIDIA H100 SXM ... $2.99 / GPU / hr" style rows.
    for m in re.finditer(
        r"(NVIDIA[\w\s-]{2,40}?)\s+.{0,200}?\$(\d+\.\d{2})\s*/\s*GPU", text
    ):
        model = canonical_model(m.group(1))
        if not model:
            continue
        offers.append(Offer(
            provider="Lambda",
            provider_slug="lambda",
            gpu_model=model,
            vram_gb=0,  # backfilled from KNOWN_VRAM below
            price_hour_usd=float(m.group(2)),
            source_url="https://lambda.ai/service/gpu-cloud",
            affiliate_url=AFFILIATE["lambda"],
        ))
    if not offers:
        raise RuntimeError("Lambda page parsed but no offers matched - selector rot?")
    return offers


KNOWN_VRAM = {
    "B200": 192, "H200": 141, "H100 SXM": 80, "H100 PCIe": 80,
    "A100 80GB": 80, "A100 40GB": 40, "L40S": 48, "RTX 6000 Ada": 48,
    "RTX A6000": 48, "RTX 5090": 32, "RTX 4090": 24,
}


def backfill_vram(offers: list[Offer]) -> list[Offer]:
    for o in offers:
        if not o.vram_gb:
            o.vram_gb = KNOWN_VRAM.get(o.gpu_model, 0)
    return offers


SCRAPERS = {
    "runpod": scrape_runpod,
    "vastai": scrape_vastai,
    "lambda": scrape_lambda,
}
