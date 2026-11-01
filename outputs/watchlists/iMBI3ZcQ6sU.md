# Martin Luk E_Main — `iMBI3ZcQ6sU`

- Watchlist name: **Martin Luk 2026-10-28 E_Main**
- Provenance: Luk/Grok MCP canonical right-sidebar **E_Main** (not Potent screener)
- VOD: SOXX short | 28 Oct 2026 (`upload_date=20261028`)

## Sections

| Section | Symbols |
|---|---|
| INDEXES | QQQ, SPY, IWM |
| LONGS | USD (Ultra Semis), SSPC, SOXS |
| SHORTS | SLV, GLD, BMNR, COIN |
| FOCUS | DRAM, UVXY |
| TRACKING | SOXX, SPCX, SNDK, SKHY, GEV, VRT, AXTI |

## TradingView import

1. Create / select watchlist named `Martin Luk 2026-10-28 E_Main`
2. Upload list… → `iMBI3ZcQ6sU.txt` or `Martin_Luk_2026-10-28_E_Main.txt`
3. Body uses short `###SECTION` headers (one file = one watchlist)

```
###INDEXES
NASDAQ:QQQ,AMEX:SPY,AMEX:IWM
###LONGS
AMEX:USD,CBOE:SSPC,AMEX:SOXS
###SHORTS
AMEX:SLV,AMEX:GLD,NYSE:BMNR,NASDAQ:COIN
###FOCUS
CBOE:DRAM,AMEX:UVXY
###TRACKING
NASDAQ:SOXX,NASDAQ:SPCX,NASDAQ:SNDK,NASDAQ:SKHY,NYSE:GEV,NYSE:VRT,NASDAQ:AXTI
```

## Regenerate locally

```bat
set TUBEON_OPENAI_API_KEY=sk-...
python scripts\watchlist_job.py iMBI3ZcQ6sU --mode auto --vision --upload-date 20261028
python scripts\watchlist_from_frames.py iMBI3ZcQ6sU --frame watchlist-frames\e_main_sidebar.png --vision
```

Potent/Leader screener is optional secondary only (`--mode screener`).
