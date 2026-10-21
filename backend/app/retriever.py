"""Knowledge-base retrieval for RAG.

Each markdown article is split into chunks (one per "## " section, prefixed with
the article title so every chunk keeps its context). Chunks are indexed with
TF-IDF and ranked by cosine similarity to the query.

TF-IDF is used instead of neural embeddings to keep the service small enough
for free hosting tiers (no PyTorch / model download). The Retriever interface
(`search`) makes it easy to swap in an embedding model later.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config


@dataclass
class Chunk:
    source: str      # file name, e.g. "vpn-connection.md"
    title: str       # article title
    section: str     # section heading
    text: str        # chunk text (title + section + body)


def chunk_markdown(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", raw, flags=re.M)
    title = title_match.group(1).strip() if title_match else path.stem
    parts = re.split(r"^## ", raw, flags=re.M)
    intro, sections = parts[0], parts[1:]
    chunks = []
    # The intro holds the title and a "Category: X" line; only index it if it has real content.
    intro_body = re.sub(r"^(# .+|Category:.*)$", "", intro, flags=re.M).strip()
    if intro_body:
        chunks.append(Chunk(path.name, title, "Overview", f"{title}\n{intro_body}"))
    for sec in sections:
        heading, _, body = sec.partition("\n")
        chunks.append(Chunk(path.name, title, heading.strip(), f"{title} - {heading.strip()}\n{body.strip()}"))
    return chunks


class Retriever:
    def __init__(self, kb_dir: Path):
        self.chunks: list[Chunk] = []
        for path in sorted(kb_dir.glob("*.md")):
            self.chunks.extend(chunk_markdown(path))
        if not self.chunks:
            raise RuntimeError(f"No knowledge base articles found in {kb_dir}")
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.matrix = self.vectorizer.fit_transform(c.text for c in self.chunks)

    def search(self, query: str, k: int = 4, min_score: float = 0.05) -> list[dict]:
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        results = []
        for i in np.argsort(scores)[::-1][:k]:
            if scores[i] < min_score:
                break
            c = self.chunks[i]
            results.append({"source": c.source, "title": c.title, "section": c.section,
                            "text": c.text, "score": round(float(scores[i]), 3)})
        return results


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever(config.KB_DIR)
