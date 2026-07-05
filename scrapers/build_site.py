"""Generate static per-GPU landing pages, sitemap.xml and robots.txt.

Runs after the scrapers in CI: reads site/data/gpus.json (+ history.json)
and writes fully static, server-rendered HTML per GPU model. These pages
are the SEO surface - crawlers get real content with prices in the HTML,
no JavaScript needed.

Usage: python scrapers/build_site.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://gpufloor.com"
SITE = Path(__file__).resolve().parent.parent / "site"

SLUGS = {
    "B200": "b200",
    "H200": "h200",
    "H100 SXM": "h100",
    "H100 PCIe": "h100-pcie",
    "A100 80GB": "a100-80gb",
    "A100 40GB": "a100-40gb",
    "L40S": "l40s",
    "RTX 6000 Ada": "rtx-6000-ada",
    "RTX A6000": "rtx-a6000",
    "RTX 5090": "rtx-5090",
    "RTX 4090": "rtx-4090",
}

BLURBS = {
    "B200": "The NVIDIA B200 is the flagship Blackwell data-centre GPU with up to 192 GB of HBM3e memory. It targets frontier-scale training and high-throughput inference, and is the fastest widely rentable GPU on the market.",
    "H200": "The NVIDIA H200 pairs the Hopper architecture with 141 GB of HBM3e, nearly doubling the H100's memory bandwidth. It shines for large-model inference and memory-bound training workloads.",
    "H100 SXM": "The NVIDIA H100 SXM is the workhorse of modern AI training: 80 GB HBM3, NVLink interconnect, and the best software support of any data-centre GPU. It remains the default choice for serious fine-tuning and multi-GPU training.",
    "H100 PCIe": "The H100 PCIe offers Hopper performance in a standard form factor. Slightly lower bandwidth than the SXM variant, but often cheaper and easier to get as a single GPU for inference and mid-size training.",
    "A100 80GB": "The NVIDIA A100 80GB is the previous-generation training flagship. Prices have fallen steadily since the H100 launch, making it strong value for fine-tuning, inference of 30-70B models, and research workloads.",
    "A100 40GB": "The A100 40GB suits inference and training of small-to-mid models. It is one of the cheapest ways to get data-centre-class reliability and software compatibility.",
    "L40S": "The NVIDIA L40S is an Ada-generation universal GPU with 48 GB. Popular for inference, fine-tuning smaller models, rendering and video workloads at a much lower price point than Hopper cards.",
    "RTX 6000 Ada": "The RTX 6000 Ada brings 48 GB and Ada-generation performance in a workstation card. A common pick for inference and development where ECC and large VRAM matter.",
    "RTX A6000": "The RTX A6000 (Ampere, 48 GB) is an older workstation card that still offers solid value for inference and experimentation thanks to its large VRAM.",
    "RTX 5090": "The GeForce RTX 5090 (Blackwell, 32 GB) is the fastest consumer GPU. On marketplaces it is a cost-effective option for inference, image/video generation and small-model fine-tuning.",
    "RTX 4090": "The GeForce RTX 4090 (24 GB) is the price-performance king of consumer GPUs for AI. Ideal for Stable Diffusion, LLM inference up to ~13B (or larger quantised), and hobby fine-tuning.",
}

CSS = """*{box-sizing:border-box;margin:0}body{background:#f2f4f5;color:#16191d;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.6}a{color:inherit}.wrap{max-width:860px;margin:0 auto;padding:0 20px}header{padding:26px 0 8px}.brand{font-family:'Space Grotesk',system-ui,sans-serif;font-weight:700;font-size:1.15rem;letter-spacing:-.02em;text-decoration:none;display:inline-block}.brand .tick{color:#3d6000}h1{font-family:'Space Grotesk',system-ui,sans-serif;font-size:1.7rem;letter-spacing:-.02em;margin:14px 0 4px}.stamp{font-family:'IBM Plex Mono',monospace;font-size:.75rem;color:#6b7480;margin-bottom:18px}.card{background:#fff;border:1px solid #e0e4e8;border-radius:10px;overflow:hidden;margin:16px 0}table{width:100%;border-collapse:collapse;font-size:.9rem}th{font-family:'IBM Plex Mono',monospace;font-weight:400;font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:#6b7480;text-align:left;padding:9px 16px;border-bottom:1px solid #e0e4e8}td{padding:10px 16px;border-bottom:1px solid #e0e4e8}tr:last-child td{border-bottom:0}td.price{font-family:'IBM Plex Mono',monospace;font-weight:600;white-space:nowrap}td.kind{font-family:'IBM Plex Mono',monospace;font-size:.75rem;color:#6b7480}tr.floor td.price{color:#3d6000}tr.floor td.price::after{content:"floor";margin-left:8px;font-size:.62rem;font-weight:600;background:#76b900;color:#fff;padding:2px 6px;border-radius:99px;vertical-align:1px}.go{font-family:'IBM Plex Mono',monospace;font-size:.75rem;text-decoration:none;border:1px solid #e0e4e8;padding:5px 10px;border-radius:8px;white-space:nowrap}.go:hover{border-color:#3d6000;color:#3d6000}main p{margin:12px 0;max-width:70ch}main h2{font-family:'Space Grotesk',system-ui,sans-serif;font-size:1.15rem;margin:26px 0 6px}nav.other{margin:30px 0;font-size:.85rem;line-height:2}nav.other a{margin-right:14px;font-family:'IBM Plex Mono',monospace;font-size:.78rem;text-decoration:none;border:1px solid #e0e4e8;padding:4px 9px;border-radius:8px;white-space:nowrap;display:inline-block}footer{padding:24px 0 40px;color:#6b7480;font-size:.78rem}"""

BEACON = """<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "36af2cd646bf4039b74f4b1d6446a233"}'></script>"""

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">'


def fmt(p: float) -> str:
    return f"${p:.2f}"


def build_page(model: str, offers: list[dict], all_models: list[str],
               generated_at: str) -> str:
    slug = SLUGS[model]
    rows = sorted(offers, key=lambda o: o["price_hour_usd"])
    floor = rows[0]
    ondemand = [o for o in rows if o["kind"] == "on-demand"]
    cheapest_od = ondemand[0] if ondemand else floor
    vram = next((o["vram_gb"] for o in rows if o["vram_gb"]), 0)
    date_h = generated_at[:10]

    title = f"Cheapest {model} Cloud GPU Price — {fmt(floor['price_hour_usd'])}/hr Compared"
    desc = (f"Live {model} rental prices compared across {len({o['provider'] for o in rows})} "
            f"cloud GPU providers. Cheapest right now: {fmt(floor['price_hour_usd'])}/hr "
            f"at {floor['provider']}. Updated daily.")

    table_rows = "".join(
        f'<tr class="{"floor" if o is rows[0] else ""}">'
        f'<td>{o["provider"]}</td>'
        f'<td class="price">{fmt(o["price_hour_usd"])}</td>'
        f'<td class="kind">{o["kind"]}</td>'
        f'<td><a class="go" href="{o.get("affiliate_url") or o["source_url"]}" '
        f'rel="sponsored noopener" target="_blank">view &rarr;</a></td></tr>'
        for o in rows
    )

    others = "".join(
        f'<a href="/{SLUGS[m]}/">{m}</a>' for m in all_models if m != model
    )

    spot_note = ""
    if len(rows) > 1 and rows[0]["kind"] != "on-demand":
        spot_note = (f" The overall floor of {fmt(floor['price_hour_usd'])}/hr is a "
                     f"{floor['kind']} offer, which can be interrupted; the cheapest "
                     f"regular on-demand price is {fmt(cheapest_od['price_hour_usd'])}/hr "
                     f"at {cheapest_od['provider']}.")

    faq_json = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [{
            "@type": "Question",
            "name": f"How much does it cost to rent an {model} GPU?",
            "acceptedAnswer": {"@type": "Answer", "text":
                f"As of {date_h}, {model} cloud rental prices start at "
                f"{fmt(floor['price_hour_usd'])} per GPU per hour at {floor['provider']}. "
                f"Prices are compared daily across providers on GPU Floor."}
        }, {
            "@type": "Question",
            "name": f"Which cloud provider has the cheapest {model}?",
            "acceptedAnswer": {"@type": "Answer", "text":
                f"{floor['provider']} currently offers the lowest {model} price at "
                f"{fmt(floor['price_hour_usd'])}/hr ({floor['kind']})."}
        }]
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{BASE_URL}/{slug}/">
{FONTS}
<style>{CSS}</style>
<script type="application/ld+json">{faq_json}</script>
{BEACON}
</head>
<body>
<div class="wrap">
<header><a class="brand" href="/">GPU<span class="tick">/</span>Floor</a></header>
<main>
<h1>{model} cloud GPU price comparison</h1>
<div class="stamp">updated {generated_at[:16].replace("T", " ")} UTC &middot; prices per GPU per hour, USD</div>

<div class="card"><table>
<thead><tr><th>provider</th><th>$/gpu/hr</th><th>type</th><th></th></tr></thead>
<tbody>{table_rows}</tbody>
</table></div>

<h2>What does an {model} cost to rent?</h2>
<p>As of {date_h}, the cheapest {model} rental is <strong>{fmt(floor["price_hour_usd"])} per GPU
per hour</strong> at {floor["provider"]}. Prices on this page are collected automatically from
each provider's public pricing and refreshed daily, so the table above reflects the current
market rather than a stale blog snapshot.{spot_note}</p>

<h2>About the {model}</h2>
<p>{BLURBS.get(model, "")}{f" It ships with {vram} GB of VRAM per GPU." if vram else ""}</p>

<h2>On-demand vs community and spot pricing</h2>
<p>On-demand instances run at a fixed rate until you stop them. Community and spot offers
(marketplaces like Vast.ai, RunPod community cloud) are often dramatically cheaper but can be
interrupted or vary in reliability between hosts. For long training runs, weigh the price gap
against the cost of checkpoint restarts; for interruptible inference and experimentation, the
cheaper tiers are usually the rational pick.</p>

<nav class="other"><h2>Compare other GPUs</h2>{others}</nav>
</main>
<footer><p>Prices are indicative and change frequently; always confirm on the provider's site.
Some links are referral links, which fund this site at no cost to you.
<a href="/">Back to the full comparison table</a>.</p></footer>
</div>
</body>
</html>
"""


def main() -> int:
    data = json.loads((SITE / "data" / "gpus.json").read_text())
    generated_at = data["generated_at"]

    by_model: dict[str, list[dict]] = {}
    for o in data["offers"]:
        if o["gpu_model"] in SLUGS:
            by_model.setdefault(o["gpu_model"], []).append(o)

    models = [m for m in SLUGS if m in by_model]
    for model in models:
        out = SITE / SLUGS[model]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            build_page(model, by_model[model], models, generated_at))
    print(f"Built {len(models)} GPU pages")

    today = datetime.now(timezone.utc).date().isoformat()
    urls = [f"{BASE_URL}/"] + [f"{BASE_URL}/{SLUGS[m]}/" for m in models]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n"
                         for u in urls)
               + "</urlset>\n")
    (SITE / "sitemap.xml").write_text(sitemap)
    (SITE / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")
    print(f"Wrote sitemap.xml ({len(urls)} urls) and robots.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
