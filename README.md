# Local TubeonAI

YouTube livestream → captions → timestamped bullets (TubeonAI-style) → Markdown + Web UI.

## Quick start

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

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
