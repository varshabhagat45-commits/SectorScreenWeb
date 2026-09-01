# Indian Sector Screen — 47-Criterion Stock Screener (static build)

A web dashboard that screens NSE stocks of a chosen sector against a
47-criterion quality/momentum model (and a bank-specific registry for
banks/NBFCs), showing verdicts (PASSED / MARGINAL / ELIMINATED), hard-gate
failures, soft flags and missing data.

## Why this is a static site
The underlying screen **scrapes Screener.in and queries Yahoo Finance per
ticker**, with 10–30 s synchronous fetches, rate-limiting sleeps and a local
disk cache. Vercel's serverless/edge runtime cannot run that (function timeouts,
no persistent disk, cloud IPs get blocked, and scraping a third-party site from a
public host violates their terms). So this repo deploys a **precomputed
snapshot**: the data is generated on your machine and served as static files.
Vercel is perfect for static hosting.

## Regenerate the data snapshot
Requires Python 3.11+ with the engine's dependencies (`pip install -r
../requirements.txt` equivalent: yfinance, pandas, beautifulsoup4, requests,
matplotlib, numpy). Fetch every sector and write `site/data/sectors.json`:

```powershell
cd "..\Pharmaceutical Screening Engine Python Script Development"
python build_data.py                     # all sectors, all modes (~10–20 min first run)
python build_data.py --sector "IT Services"   # one sector, faster
```

The script caches to `cache/`, so re-runs are quick. Check `site/data/sectors.json`
exists before deploying.

## Deploy to GitHub
1. Create an empty repo on GitHub (e.g. `SectorScreenWeb`, private or public).
2. From this folder:
   ```powershell
   git init
   git add .
   git commit -m "Indian sector screen - static dashboard"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USER>/SectorScreenWeb.git
   git push -u origin main
   ```

## Deploy to Vercel
1. Sign up / log in at https://vercel.com (GitHub login recommended).
2. **Add New → Project → Import** the `SectorScreenWeb` GitHub repo.
3. Vercel reads `vercel.json` (static, `outputDirectory: site`). Accept defaults → **Deploy**.
4. You get a URL like `https://SectorScreenWeb.vercel.app`.

## What the dashboard shows
- Pick a **sector** and **mode** (strict / quality_first / sector_adjusted).
- Verdict counts, results table (per company: G1/G2, failures, market cap,
  hard-fail and soft-flag pills, missing count), hard-gate detail, top-five chart.
- Bank/NBFC sectors use a bank-specific registry; capital-intensive sectors show
  a leverage caveat.

## Important
- Data is a **snapshot** at `as_of`; not live. Regenerate to refresh.
- Research / education only — **not personalized investment advice**.
- Many tickers' fundamentals on Screener are masked (surfaced as fetch errors);
  the snapshot only includes publicly available ones.
