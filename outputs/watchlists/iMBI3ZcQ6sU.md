# Martin Luk on-screen list — `iMBI3ZcQ6sU`

- Provenance: **vision/human Symbol-column read** of best frame `data/frames/iMBI3ZcQ6sU/screener/1-18-32.jpg` (Luk/Tube report). **Not** RapidOCR (that produced KK/LM junk).
- Title: SOXX short | 28 Oct 2026
- Symbols: **27** (Leader table). Detail panel also showed **BRZE** @ ~45.85 (not mixed into wipe).

## Tickers

AXSM, GNS, ICLR, EVR, WMG, TXG, BYON, TWST, TEM, PPG, CRL, FRO, ACN, PNT, REVV, MRNA, NTRA, HCA, ETSY, IQV, SOFI, GH, EXAS, RBRK, AKAM, Z, MNSO

## TradingView import

Watchlist → Upload list… → pick `iMBI3ZcQ6sU.txt`

```
###Martin Luk iMBI3ZcQ6sU Leader
NASDAQ:AXSM,NYSE:GNS,NASDAQ:ICLR,NYSE:EVR,NASDAQ:WMG,NASDAQ:TXG,NYSE:BYON,NASDAQ:TWST,NASDAQ:TEM,NYSE:PPG,NYSE:CRL,NYSE:FRO,NYSE:ACN,NASDAQ:PNT,NASDAQ:REVV,NASDAQ:MRNA,NASDAQ:NTRA,NYSE:HCA,NASDAQ:ETSY,NYSE:IQV,NASDAQ:SOFI,NASDAQ:GH,NASDAQ:EXAS,NYSE:RBRK,NASDAQ:AKAM,NASDAQ:Z,NYSE:MNSO
```

## Regenerate locally

```bat
set TUBEON_OPENAI_API_KEY=sk-...
python scripts\watchlist_from_frames.py iMBI3ZcQ6sU --frame data\frames\iMBI3ZcQ6sU\screener\1-18-32.jpg --vision
```
