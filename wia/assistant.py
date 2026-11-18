"""The main pipeline: retrieve -> guardrails -> generate -> validate -> log -> review.

    question
       |
    [1] retrieve top-k chunks from APPROVED, latest-revision docs only
       |
    [2] if best score < MIN_SCORE  -> refuse ("not in approved documents"), no LLM call
       |
    [3] Claude answers with forced structured output (JSON schema)
       |
    [4] validate citations: every cited doc/revision must be one we actually retrieved
       |
    [5] low confidence or bad citations -> send to human review queue
       |
    [6] write everything to the audit log
"""
import logging

from . import config
from .documents import build_chunks, controlled_set, load_all
from .retriever import TfidfRetriever
from .review import ReviewQueue, audit
from .schemas import AskResponse, Citation, LLMAnswer, RetrievedChunk

log = logging.getLogger(__name__)


class Assistant:
    def __init__(self, llm, docs_dir=None, review_queue: ReviewQueue | None = None,
                 top_k: int | None = None, min_score: float | None = None):
        self.llm = llm
        self.docs_dir = docs_dir or config.DOCS_DIR
        self.top_k = top_k or config.TOP_K
        self.min_score = config.MIN_SCORE if min_score is None else min_score
        self.reviews = review_queue or ReviewQueue()
        self.reload()

    def reload(self) -> None:
        """(Re)index documents. Call after documents change."""
        all_docs = load_all(self.docs_dir)
        self.documents = controlled_set(all_docs)
        self.chunks = build_chunks(self.documents)
        self.retriever = TfidfRetriever(self.chunks)
        excluded = [f"{d['doc_id']} rev {d['revision']} ({d['status']})"
                    for d in all_docs if d not in self.documents]
        log.info("Indexed %d docs / %d chunks. Excluded: %s", len(self.documents), len(self.chunks), excluded)

    # ---- tools also exposed over MCP -------------------------------------------------
    def search(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        return self.retriever.search(query, k or self.top_k)

    def get_document(self, doc_id: str) -> dict | None:
        for d in self.documents:
            if d["doc_id"].lower() == doc_id.lower():
                return {k: v for k, v in d.items() if k != "file"}
        return None

    # ---- main entry point ------------------------------------------------------------
    def ask(self, question: str, user: str = "anonymous") -> AskResponse:
        question = question.strip()
        if not question:
            raise ValueError("Question is empty.")

        chunks = self.search(question)
        considered = [f"{c.doc_id} rev {c.revision} / {c.section} ({c.score})" for c in chunks]

        # Guardrail 1: nothing relevant enough -> refuse without calling the LLM.
        if not chunks or chunks[0].score < self.min_score:
            resp = AskResponse(
                question=question,
                answer="I could not find this in the approved work instructions. "
                       "Please check with the responsible engineer.",
                citations=[], confidence="low", insufficient_information=True,
                status="refused", sources_considered=considered,
            )
            audit("ask", user=user, question=question, status=resp.status, sources=considered)
            return resp

        llm_answer: LLMAnswer = self.llm.answer(question, chunks)

        # Guardrail 2: citations must point to chunks we actually gave the model.
        warnings = []
        allowed = {(c.doc_id, c.revision) for c in chunks}
        valid_citations: list[Citation] = []
        for cit in llm_answer.citations:
            if (cit.doc_id, cit.revision) in allowed:
                valid_citations.append(cit)
            else:
                warnings.append(f"Dropped citation not in retrieved sources: {cit.doc_id} rev {cit.revision}")

        if llm_answer.insufficient_information:
            status = "refused"
        elif not valid_citations:
            warnings.append("Answer has no valid citation.")
            status = "needs_review"
        elif llm_answer.confidence == "low" or warnings:
            status = "needs_review"
        else:
            status = "answered"

        resp = AskResponse(
            question=question, answer=llm_answer.answer, citations=valid_citations,
            confidence=llm_answer.confidence,
            insufficient_information=llm_answer.insufficient_information,
            status=status, warnings=warnings, sources_considered=considered,
        )

        # Guardrail 3: uncertain answers go to a human before anyone relies on them.
        if status == "needs_review":
            resp.review_id = self.reviews.submit(question, resp.model_dump(), reason="; ".join(warnings) or "low confidence")

        audit("ask", user=user, question=question, status=status,
              citations=[c.model_dump() for c in valid_citations], warnings=warnings, sources=considered)
        return resp
