# GPU Floor — cloud GPU price tracker

Self-updating comparison site for cloud GPU hourly prices. Zero servers:
GitHub Actions runs the scrapers twice a day, commits `site/data/gpus.json`,
and Cloudflare Pages redeploys the static site on every commit.

## Layout

```
scrapers/
  common.py      shared schema, model-name normalisation, output writer
  providers.py   one scraper per provider (RunPod, Vast.ai, Lambda)
  run_all.py     runner; --sample writes offline dev data
site/
  index.html     the whole frontend (no build step)
  data/gpus.json generated price data
.github/workflows/update-prices.yml
```

## Local development

```bash
pip install requests
python scrapers/run_all.py --sample     # offline sample data
python scrapers/run_all.py              # live scrape (verify endpoints first!)
cd site && python -m http.server 8080   # open http://localhost:8080
```

## Before first deploy — do these

1. **Verify every endpoint.** The RunPod GraphQL query, Vast.ai bundles API and
   Lambda pricing page were written blind; response shapes change. Run each
   scraper, inspect output, fix field names.
2. **Check ToS.** Read each provider's terms on automated access. Many GPU
   clouds actively *want* to appear in comparisons (it drives signups), and
   several have referral programmes — when in doubt, email them; a blessed
   API beats a scraper.
3. **Set a real contact** in the User-Agent in `providers.py`.

## Deploy

1. Push this repo to GitHub.
2. Cloudflare Pages → connect repo → build command: *(none)*,
   output directory: `site`.
3. Point your domain at it. Enable the Actions workflow.

## Monetisation roadmap

- **Phase 1 (launch):** referral programmes. RunPod, Vast.ai and most smaller
  GPU clouds have them; paste links into `AFFILIATE` in `providers.py`.
  Links already carry `rel="sponsored"`.
- **Phase 2 (some traffic):** Google AdSense. Ad slot placeholder exists in
  `index.html` (`#ad-top`). AdSense wants original content, so add a few
  explainer pages first ("H100 vs H200 for fine-tuning", "spot vs on-demand").
- **Phase 3:** price-history charts (start persisting daily snapshots now —
  cheap to store, impossible to backfill later) and a price-drop alert
  email list. The alert list is the real long-term asset.

## Growth notes

- Every explainer page targets one long-tail search ("cheapest H100",
  "vast.ai vs runpod"). The table is the anchor; pages bring the traffic.
- Post genuinely useful price-drop observations to r/MachineLearning,
  Hacker News, X. Data sites grow on "look at this chart" moments.
- Add providers over time (Nebius, Crusoe, Together, Hyperstack, DataCrunch,
  Genesis Cloud…). Each new provider = new comparison keywords.
