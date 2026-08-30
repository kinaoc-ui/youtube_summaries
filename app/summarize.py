from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .asr_fix import fix_asr
from .config import settings

SKIP_PATTERNS = [
    r"^good (morning|afternoon|evening)",
    r"^hello everyone",
    r"^i want to feel$",
    r"^guess what\??$",
    r"^he$",
    r"^oh\.?$",
    r"^yeah\.?$",
]


SYSTEM_PROMPT = """You summarize YouTube trading livestream transcripts into TubeonAI-style bullets.
Rules:
- One short English sentence per chunk.
- Keep tickers, prices, EMAs, VWAP, support/resistance exactly.
- ONLY name a ticker if that exact token (or a listed ASR alias already corrected in the text) appears in THIS chunk. Never invent tickers from similar-sounding words (e.g. octaves≠OKTA, socket→SOXX only if text says socket/SOXX).
- Fix obvious ASR ticker errors when clear (SNTK/SMTK→SNDK, Iron Yen/hour and a cube→IREN, sapce/space x→SPCX, fake→FIG only when Figma not 'fake out', Call Vith/Corvif→CRWV, D-talk→DDOG, WODF→HOOD, All NDS→ONDS).
- If he talks a different ticker than the chart, keep both (do not overwrite the chart).
- Skip pure greetings / silence / filler.
- Output ONLY lines like: 04:46 Focus on short side; limited buying power, pick 1–2 names.
- No markdown fences, no commentary outside the bullet lines.
"""


def _is_skip(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < 12:
        return True
    return any(re.search(p, t) for p in SKIP_PATTERNS)


def _compress_offline(text: str, max_len: int = 160) -> str:
    text = fix_asr(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Prefer first meaningful clause-ish segment
    parts = re.split(r"(?<=[.!?])\s+|,\s+(?=[A-Z])", text)
    keep: list[str] = []
    for p in parts:
        p = p.strip(" ,")
        if not p or _is_skip(p):
            continue
        keep.append(p)
        joined = " ".join(keep)
        if len(joined) >= 80:
            break
    out = " ".join(keep) if keep else text
    if len(out) > max_len:
        out = out[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return out


def summarize_chunks_offline(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    bullets: list[dict[str, str]] = []
    for c in chunks:
        text = c.get("text", "")
        if _is_skip(text):
            continue
        line = _compress_offline(text)
        if _is_skip(line):
            continue
        bullets.append({"t": c["t"], "start": c["start"], "text": line})
    return bullets


async def _chat_openai_compatible(base_url: str, api_key: str, model: str, user: str) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()


async def _chat_ollama(model: str, user: str) -> str:
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        return data["message"]["content"].strip()


def _parse_bullet_lines(raw: str, fallback_chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    bullets: list[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-•").strip()
        m = re.match(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$", line)
        if not m:
            continue
        bullets.append({"t": m.group(1), "text": m.group(2).strip(), "start": 0})
    if bullets:
        # attach start from matching chunk timestamp when possible
        by_t = {c["t"]: c["start"] for c in fallback_chunks}
        for b in bullets:
            b["start"] = by_t.get(b["t"], 0)
        return bullets
    return summarize_chunks_offline(fallback_chunks)


async def summarize_chunks_llm(chunks: list[dict[str, Any]], provider: str | None = None) -> list[dict[str, str]]:
    provider = (provider or settings.llm_provider).lower()
    if provider == "offline":
        return summarize_chunks_offline(chunks)

    # Batch chunks to keep prompts manageable
    batch_size = 12
    all_bullets: list[dict[str, str]] = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        body = "\n\n".join(f"[{c['t']}] {fix_asr(c['text'])}" for c in batch)
        user = f"Summarize these transcript chunks:\n\n{body}"
        if provider == "ollama":
            raw = await _chat_ollama(settings.ollama_model, user)
        elif provider == "openai":
            raw = await _chat_openai_compatible(
                settings.openai_base_url,
                settings.openai_api_key,
                settings.openai_model,
                user,
            )
        else:
            raise ValueError(f"Unknown llm provider: {provider}")
        all_bullets.extend(_parse_bullet_lines(raw, batch))
    return all_bullets


def bullets_to_markdown(
    video_id: str,
    title: str,
    bullets: list[dict[str, str]],
    executive: dict[str, Any] | None = None,
    source: str = "agent",
) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    lines = [
        f"# {title}",
        "",
        f"- **Video:** [{video_id}]({url})",
        f"- **Source:** {source}",
        "",
    ]
    if executive:
        lines += ["## Executive summary", ""]
        for k, v in executive.items():
            if isinstance(v, list):
                lines.append(f"- **{k}:** {', '.join(str(x) for x in v)}")
            else:
                lines.append(f"- **{k}:** {v}")
        lines.append("")
    lines += ["## Timestamped notes", ""]
    for b in bullets:
        lines.append(f"- `{b['t']}` {b['text']}")
    lines.append("")
    return "\n".join(lines)


def parse_markdown_bullets(md: str) -> list[dict[str, str]]:
    bullets: list[dict[str, str]] = []
    for line in md.splitlines():
        m = re.match(r"^-\s+`([^`]+)`\s+(.+)$", line.strip())
        if m:
            bullets.append({"t": m.group(1), "text": m.group(2), "start": 0})
    return bullets
