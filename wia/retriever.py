"""Retrieval step of RAG.

MVP uses TF-IDF + cosine similarity (scikit-learn): fast, free, explainable, and
needs no external service. The interface (search(query, k)) is the same one a
vector database (Chroma, pgvector, FAISS) would plug into later.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .schemas import Chunk, RetrievedChunk


class TfidfRetriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("No chunks to index - check the docs folder.")
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
        # Index title + section + text so headings help matching.
        corpus = [f"{c.title} {c.section} {c.text}" for c in chunks]
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, k: int = 4) -> list[RetrievedChunk]:
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        ranked = scores.argsort()[::-1][:k]
        return [
            RetrievedChunk(**self.chunks[i].model_dump(), score=round(float(scores[i]), 4))
            for i in ranked if scores[i] > 0
        ]
