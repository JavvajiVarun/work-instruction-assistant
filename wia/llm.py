"""Generation step of RAG, using Claude with a forced tool call for structured output.

Forcing the model to call `submit_answer` means we always get JSON that matches
LLMAnswer's schema, instead of free text we'd have to parse.
"""
import json
import logging

from pydantic import ValidationError

from . import config
from .schemas import LLMAnswer, RetrievedChunk

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You help technicians and engineers at an industrial facility find information in
CONTROLLED work instructions.

Rules:
- Answer ONLY from the SOURCES provided. Never use outside knowledge for procedures or values.
- Every fact in your answer must be cited with doc_id, revision and section.
- Quote numeric values (torque, temperature, limits) exactly as written in the source.
- If the sources do not contain the answer, set insufficient_information=true and say so plainly.
- You give information only. You never approve work or change procedures.
- Keep answers short and practical."""

ANSWER_TOOL = {
    "name": "submit_answer",
    "description": "Return the grounded answer with citations.",
    # Written out explicitly (no $ref) so it matches LLMAnswer and is easy to read.
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "Short, direct answer for a technician."},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "revision": {"type": "string"},
                        "section": {"type": "string"},
                    },
                    "required": ["doc_id", "revision", "section"],
                },
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "insufficient_information": {"type": "boolean"},
        },
        "required": ["answer", "citations", "confidence", "insufficient_information"],
    },
}


def format_sources(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[SOURCE doc_id={c.doc_id} revision={c.revision} section=\"{c.section}\"]\n"
        f"Title: {c.title}\n{c.text}"
        for c in chunks
    )


class ClaudeLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        import anthropic  # imported here so tests run without the SDK configured

        key = api_key or config.ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
        self.client = anthropic.Anthropic(api_key=key, timeout=30.0, max_retries=2)
        self.model = model or config.ANTHROPIC_MODEL

    def answer(self, question: str, chunks: list[RetrievedChunk]) -> LLMAnswer:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            tools=[ANSWER_TOOL],
            tool_choice={"type": "tool", "name": "submit_answer"},
            messages=[{
                "role": "user",
                "content": f"SOURCES:\n{format_sources(chunks)}\n\nQUESTION: {question}",
            }],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_answer":
                try:
                    return LLMAnswer.model_validate(block.input)
                except ValidationError as e:
                    log.error("LLM output failed schema validation: %s", e)
                    raise
        raise RuntimeError("Model did not return a submit_answer tool call.")


class FakeLLM:
    """Deterministic stand-in used by tests and by `--offline` demo mode (no API key needed).
    It 'answers' with the top retrieved chunk so the rest of the pipeline can be exercised."""

    def answer(self, question: str, chunks: list[RetrievedChunk]) -> LLMAnswer:
        if not chunks:
            return LLMAnswer(answer="Not found in the approved documents.", insufficient_information=True)
        top = chunks[0]
        return LLMAnswer(
            answer=f"[offline mode] From {top.doc_id} Rev {top.revision}, '{top.section}': {top.text[:300]}",
            citations=[{"doc_id": top.doc_id, "revision": top.revision, "section": top.section}],
            confidence="medium",
        )


def to_json(answer: LLMAnswer) -> str:
    return json.dumps(answer.model_dump(), indent=2)
