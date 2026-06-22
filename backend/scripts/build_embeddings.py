"""
build_embeddings.py — offline corpus embedder for the RAG pipeline.

Run this ONCE manually before the demo:

    cd backend
    set HF_TOKEN=hf_xxx     (Windows)  /  export HF_TOKEN=hf_xxx (mac/linux)
    python scripts/build_embeddings.py

What it does:
1. Loads backend/data/seed_corpus.json
2. Embeds each item via Hugging Face Inference API
   (sentence-transformers/all-MiniLM-L6-v2)
3. Writes vectors + metadata to backend/data/corpus_embeddings.json

This script does NOT run during the demo. The runtime backend reads
corpus_embeddings.json and falls back to keyword search if it is missing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "data" / "seed_corpus.json"
OUT_PATH = ROOT / "data" / "corpus_embeddings.json"


def embed(text: str, token: str, retries: int = 3) -> list[float]:
    payload = json.dumps({"inputs": text, "options": {"wait_for_model": True}}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(HF_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # all-MiniLM-L6-v2 returns a flat list[float] for a single input
            if isinstance(data, list) and data and isinstance(data[0], (int, float)):
                return [float(x) for x in data]
            # Some HF responses wrap a single vector in a list
            if isinstance(data, list) and data and isinstance(data[0], list):
                return [float(x) for x in data[0]]
            raise RuntimeError(f"Unexpected HF response shape: {type(data)}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"HF embedding failed after {retries} retries: {last_err}")


def main() -> int:
    token = os.getenv("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN environment variable is required.", file=sys.stderr)
        return 1

    if not CORPUS_PATH.exists():
        print(f"ERROR: corpus not found at {CORPUS_PATH}", file=sys.stderr)
        return 1

    with CORPUS_PATH.open("r", encoding="utf-8") as f:
        corpus = json.load(f)

    out: list[dict] = []
    for i, item in enumerate(corpus):
        text = f"{item.get('title', '')}. Skills: {', '.join(item.get('skills', []))}. {item.get('description', '')}"
        print(f"[{i + 1}/{len(corpus)}] embedding {item.get('id')}...")
        vec = embed(text, token)
        out.append({
            "id": item.get("id"),
            "type": item.get("type"),
            "title": item.get("title"),
            "skills": item.get("skills", []),
            "description": item.get("description", ""),
            "embedding": vec,
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump({"model": HF_MODEL, "items": out}, f)

    print(f"Wrote {len(out)} embeddings to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
