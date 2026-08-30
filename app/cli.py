from __future__ import annotations

import argparse
import asyncio

from .config import ensure_dirs, settings
from .storage import save_summary
from .summarize import bullets_to_markdown, summarize_chunks_llm
from .transcript import chunk_transcript, extract_video_id, fetch_transcript, save_transcript


async def run(url: str, provider: str, title: str | None) -> None:
    ensure_dirs()
    video_id = extract_video_id(url)
    print(f"Fetching transcript for {video_id}…")
    snippets = fetch_transcript(video_id)
    chunks = chunk_transcript(snippets, settings.chunk_seconds)
    save_transcript(video_id, snippets, chunks)
    print(f"Chunks: {len(chunks)} | provider: {provider}")
    bullets = await summarize_chunks_llm(chunks, provider=provider)
    md = bullets_to_markdown(
        video_id,
        title or f"YouTube {video_id}",
        bullets,
        source=f"cli-{provider}",
    )
    paths = save_summary(video_id, md, meta={"title": title, "provider": provider})
    print(f"Saved: {paths['output']}")
    print(f"Bullets: {len(bullets)}")


def main() -> None:
    p = argparse.ArgumentParser(description="Local TubeonAI CLI")
    p.add_argument("url", help="YouTube URL or video id")
    p.add_argument("--provider", default=settings.llm_provider, choices=["offline", "ollama", "openai"])
    p.add_argument("--title", default=None)
    args = p.parse_args()
    asyncio.run(run(args.url, args.provider, args.title))


if __name__ == "__main__":
    main()
