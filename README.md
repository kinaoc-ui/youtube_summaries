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
