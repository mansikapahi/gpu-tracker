"""Provider scrapers.

Design rules:
- Each scraper is a function returning list[Offer]; it must raise on failure
  (run_all.py catches per-provider, so one broken provider never kills the run).
- Prefer JSON APIs over HTML scraping; HTML breaks silently and often.
"""
from __future__ import annotations

import re

import requests

from common import Offer, canonical_model

HEADERS = {"User-Agent": "gpu-price-tracker/0.1 (contact: gpufloor.com)"}
TIMEOUT = 30

# Put your referral links here once you're accepted into partner programmes.
AFFILIATE = {
    "runpod": "https://runpod.io?ref=6vbvms6s",   # e.g. "https://runpod.io?ref=XXXX"
    "vastai": "https://cloud.vast.ai/?ref_id=606541",
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
    """Parse Lambda's public pricing page (lambda.ai/pricing).

    Instance rows look like: NVIDIA H100 SXM | 80 GB | ... | $3.99
    (price per GPU per hour). Cluster rows have no 'NN GB' VRAM
    column, so the regex naturally skips them.
    """
    resp = requests.get("https://lambda.ai/pricing",
                        headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    text = re.sub(r"<[^>]+>", " ", resp.text)
    text = re.sub(r"\s+", " ", text)

    offers: list[Offer] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"NVIDIA\s+([A-Za-z0-9 .]+?)\s+(\d{2,3})\s*GB\s+[^$]{0,120}?\$(\d+\.\d{2})",
        text,
    ):
        name, vram, price = m.group(1), int(m.group(2)), float(m.group(3))
        model = canonical_model(f"{name} {vram}")
        if not model or model in seen:
            continue
        seen.add(model)
        offers.append(Offer(
            provider="Lambda",
            provider_slug="lambda",
            gpu_model=model,
            vram_gb=vram,
            price_hour_usd=price,
            source_url="https://lambda.ai/pricing",
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
