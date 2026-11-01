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

Martin 嘅 **主清單** 係 chart 右欄 **E_Main**（`INDEXES` / `LONGS` / `SHORTS` / `FOCUS` / `TRACKING`），唔係 Potent/Leader screener 表。Potent 只係 optional secondary（`--mode screener`）。

**策略（default `--mode auto`）：**
1. 截 chart frames + 右欄 `*_wl.jpg` crop
2. OCR/vision 讀 E_Main section headers → 分桶
3. 一個 Upload `.txt`：短 `###INDEXES` / `###LONGS` / …（dated 名喺 filename / TV list name，唔重複寫入每個 header）
4. Watchlist 名：`Martin Luk YYYY-MM-DD E_Main`（用 VOD `upload_date`，唔用 run date）
5. 需要 vision 時設 `TUBEON_OPENAI_API_KEY`（或 `TUBEON_VISION_OLLAMA_MODEL`）

```bash
set TUBEON_OPENAI_API_KEY=sk-...
python scripts/watchlist_job.py <videoId> --mode auto --force --vision --upload-date 20261028

# iMBI3ZcQ6sU sample
cd /d "C:\Users\kinao\OneDrive\桌面\stock\youtube"
run_watchlist_imbi.bat
python scripts\watchlist_from_frames.py iMBI3ZcQ6sU --frame watchlist-frames\e_main_sidebar.png --vision

# Potent secondary only
python scripts/watchlist_job.py <videoId> --mode screener

# Martin daily 自動 kick E_Main
python scripts/martin_daily.py
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
| `outputs/watchlists/<id>.txt` | TradingView **Upload list…** |
| `outputs/watchlists/Martin_Luk_<date>_E_Main.txt` | 同內容、dated 檔名 |
| `outputs/watchlists/<id>.md` | 可讀表 |
| `data/frames/<id>/tail/*_wl.jpg` | 右欄 crop（gitignore） |

**Import 去 TV：** 開／揀清單名 `Martin Luk YYYY-MM-DD E_Main` → **Upload list…** → 揀 `.txt`。**無公開 TradingView API**；Essential+ 先有 Upload。

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
