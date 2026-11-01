# Local TubeonAI

YouTube livestream → captions → timestamped bullets (TubeonAI-style) → Markdown + Web UI.

## Quick start

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

## Phone（Streamlit Cloud）

同 screening 一樣：GitHub push → Cloud 自動更新。電話開 Cloud link，撳時間跳 YouTube。

1. [share.streamlit.io](https://share.streamlit.io) 用 GitHub 登入 → **New app**
2. **Repository：** `kinaoc-ui/youtube_summaries`
3. **Branch：** `main`
4. **Main file path：** `phone/app.py`（唔好揀根目錄 `requirements.txt`，嗰份有 Whisper）
5. Deploy 完書籤條 `https://xxxxx.streamlit.app`

本機試：`streamlit run streamlit_app.py`

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

## CLI

```bash
python -m app.cli "https://www.youtube.com/watch?v=ufN4u_ncWZg" --provider offline
python -m app.cli "URL" --provider ollama --title "Martin Luk"
```

## Martin on-screen watchlist → TradingView

Martin Luk（`@martinlukkt`）會開 **TradingView Leader / screener 表**（好多 Symbol 行），有時仲會撳開單一隻嘅 detail panel（例如 BRZE @45.85）。字幕未必讀到表內清單，所以用畫面截圖 + OCR。

**策略（default `--mode screener`）：**
1. 全片粗掃 + 語音/摘要 hint 附近加密（唔死跟尾 10 分鐘右欄）
2. RapidOCR boxes → 最左 **Symbol column**，再經 **US allowlist** 過濾（甩掉 KK / LM / A.M 呢啲 junk）
3. 有 API key 時：**vision/LLM** 讀最高分 screener frames（優先過 OCR）；detail panel（BRZE）唔會覆蓋 table
4. 無 vision 時只輸出 allowlist 命中嘅 symbols（validated subset，唔發明 ticker）

```bash
# 推薦：Leader/screener + vision（要 OpenAI key 或 ollama vision model）
set TUBEON_OPENAI_API_KEY=sk-...
python scripts/watchlist_job.py <videoId> --mode screener --force --vision

# iMBI3ZcQ6sU — Luk 本機（已有 frames 可跳過下載）
cd /d "C:\Users\kinao\OneDrive\桌面\stock\youtube"
run_watchlist_imbi.bat
python scripts\watchlist_from_frames.py iMBI3ZcQ6sU --vision
python scripts\watchlist_from_frames.py iMBI3ZcQ6sU --frame data\frames\iMBI3ZcQ6sU\screener\1-18-32.jpg --vision

# 舊行為（只截尾 N 分鐘右欄）
python scripts/watchlist_job.py <videoId> --mode tail --last-minutes 12

# Martin daily 會自動 kick；亦可手動
python scripts/martin_daily.py --watchlist-id <videoId>
```

若 YouTube 報 bot check，設 Netscape cookies：

```bat
set TUBEON_YT_COOKIES=C:\path\to\cookies.txt
```

輸出：

| Path | 用途 |
|---|---|
| `data/summaries/<id>.watchlist.json` | 符號清單（可 push / 電話 UI） |
| `outputs/watchlists/<id>.txt` | TradingView **Upload list…** 用 |
| `outputs/watchlists/<id>.md` | 可讀表 |
| `data/frames/<id>/screener/*.jpg` | 本機截圖（gitignore） |

**Import 去 TV：** Watchlist 面板 → 撳清單名 → **Upload list…** → 揀 `.txt`。格式係官方要求嘅 `EXCHANGE:SYMBOL`、逗號分隔（可有 `###Section`）。**無公開 TradingView API**；Essential+ 先有 Upload。Web：`POST/GET /api/watchlist/{id}`，下載 `/api/watchlist/{id}/tradingview.txt`。

## Summarizer modes

| Provider | Env / setting | Notes |
|---|---|---|
| `offline` | default | Uses cached agent markdown when present; else extractive cleanup |
| `ollama` | `TUBEON_LLM_PROVIDER=ollama` | Local LLM via Ollama chat API |
| `openai` | `TUBEON_OPENAI_API_KEY=…` | Any OpenAI-compatible endpoint |

Example `.env`:

```env
TUBEON_LLM_PROVIDER=ollama
TUBEON_OLLAMA_MODEL=qwen2.5:7b
TUBEON_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

## Layout

- `app/` — FastAPI + transcript/summarize pipeline
- `static/` — Web UI
- `data/transcripts/` — cached captions JSON
- `data/summaries/` + `outputs/` — markdown digests

## Demo

`ufN4u_ncWZg` was summarized with the Cursor agent model from auto-captions and saved to `outputs/ufN4u_ncWZg.md`.
