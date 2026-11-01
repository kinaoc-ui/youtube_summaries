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

Martin Luk（`@martinlukkt`）成日喺 livestream **最後 ~10 分鐘** 開 leading / mediocre / lagging 清單；字幕未必讀到，所以用畫面截圖 + OCR。

```bash
# Standalone（重用 app/video_check 下載 360p + RapidOCR）
python scripts/watchlist_job.py <videoId>
python scripts/watchlist_job.py <videoId> --last-minutes 12 --interval 15

# 或者連埋 ASR 畫面核對一齊跑
python scripts/vision_job.py <videoId> --watchlist

# Martin daily 會自動 kick watchlist_job；亦可手動
python scripts/martin_daily.py --watchlist-id <videoId>
```

輸出：

| Path | 用途 |
|---|---|
| `data/summaries/<id>.watchlist.json` | 符號清單（可 push / 電話 UI） |
| `outputs/watchlists/<id>.txt` | TradingView **Upload list…** 用 |
| `outputs/watchlists/<id>.md` | 可讀表 |
| `data/frames/<id>/tail/*.jpg` | 本機截圖（gitignore） |

**Import 去 TV：** Watchlist 面板 → 撳清單名 → **Upload list…** → 揀 `.txt`。格式係官方要求嘅 `EXCHANGE:SYMBOL`、逗號分隔（可有 `###Section`）。**無公開 TradingView API** 可以程式化改 watchlist；付費 Essential+ 先有 Upload。Web UI：`POST/GET /api/watchlist/{id}`，下載 `/api/watchlist/{id}/tradingview.txt`。

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
