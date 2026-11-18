"""REST API (FastAPI). Run:  uvicorn wia.api:app --reload   then open http://localhost:8000/docs"""
import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .assistant import Assistant
from .llm import ClaudeLLM, FakeLLM
from .schemas import AskResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Work Instruction Assistant", version="0.1.0")
_assistant: Assistant | None = None


def get_assistant() -> Assistant:
    global _assistant
    if _assistant is None:
        llm = FakeLLM() if os.getenv("WIA_OFFLINE") == "1" else ClaudeLLM()
        _assistant = Assistant(llm=llm)
    return _assistant


class AskRequest(BaseModel):
    question: str
    user: str = "anonymous"


class DecisionRequest(BaseModel):
    approve: bool
    reviewer: str
    comment: str = ""


@app.get("/health")
def health():
    a = get_assistant()
    return {"status": "ok", "documents": len(a.documents), "chunks": len(a.chunks)}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        return get_assistant().ask(req.question, user=req.user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # upstream LLM/API failures
        logging.exception("ask failed")
        raise HTTPException(502, f"Answer generation failed: {type(e).__name__}")


@app.get("/documents")
def documents():
    return [{k: v for k, v in d.items() if k not in ("body", "file")} for d in get_assistant().documents]


@app.get("/reviews")
def reviews(status: str | None = "pending"):
    return get_assistant().reviews.list(status)


@app.post("/reviews/{review_id}/decision")
def decide(review_id: int, req: DecisionRequest):
    try:
        return get_assistant().reviews.decide(review_id, req.approve, req.reviewer, req.comment)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/reload")
def reload():
    get_assistant().reload()
    return health()
