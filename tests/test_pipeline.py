"""Unit tests. Run: pytest -q   (no API key needed; the LLM is faked)."""
import pytest

from wia import config
from wia.assistant import Assistant
from wia.documents import build_chunks, controlled_set, load_all, split_sections
from wia.llm import FakeLLM
from wia.review import ReviewQueue
from wia.schemas import LLMAnswer


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDIT_LOG", tmp_path / "audit.jsonl")
    return ReviewQueue(tmp_path / "test.db")


@pytest.fixture
def assistant(queue):
    return Assistant(llm=FakeLLM(), review_queue=queue)


# ---------- configuration control ----------
def test_only_latest_approved_revision_is_indexed():
    docs = controlled_set(load_all(config.DOCS_DIR))
    ids = {(d["doc_id"], d["revision"]) for d in docs}
    assert ("WI-101", "C") in ids
    assert ("WI-101", "B") not in ids        # superseded
    assert not any(d["doc_id"] == "WI-520" for d in docs)  # draft


def test_sections_are_split_on_headings():
    sections = split_sections("# A\nline1\n# B\nline2")
    assert sections == [("A", "line1"), ("B", "line2")]


def test_every_chunk_has_traceable_metadata():
    for c in build_chunks(controlled_set(load_all(config.DOCS_DIR))):
        assert c.doc_id and c.revision and c.section and c.status == "approved"


# ---------- retrieval ----------
def test_retrieval_finds_current_torque_section(assistant):
    top = assistant.search("bearing housing bolt torque")[0]
    assert top.doc_id == "WI-101" and top.revision == "C"
    assert "52" in top.text


def test_off_topic_question_is_refused_without_llm(assistant):
    class ExplodingLLM:
        def answer(self, *a, **k):
            raise AssertionError("LLM should not be called")
    assistant.llm = ExplodingLLM()
    resp = assistant.ask("What is the cafeteria lunch menu today?")
    assert resp.status == "refused"


# ---------- guardrails on LLM output ----------
class StubLLM:
    def __init__(self, answer: LLMAnswer):
        self._a = answer

    def answer(self, *a, **k):
        return self._a


def test_hallucinated_citation_is_dropped_and_sent_to_review(assistant, queue):
    assistant.llm = StubLLM(LLMAnswer(
        answer="Use 45 N·m.", confidence="high",
        citations=[{"doc_id": "WI-101", "revision": "B", "section": "Bearing Housing Bolt Torque"}],
    ))
    resp = assistant.ask("bearing housing bolt torque")
    assert resp.citations == []
    assert resp.status == "needs_review"
    assert resp.review_id is not None
    assert len(queue.list("pending")) == 1


def test_good_answer_is_released(assistant):
    assistant.llm = StubLLM(LLMAnswer(
        answer="Torque to 52 N·m in a star pattern.", confidence="high",
        citations=[{"doc_id": "WI-101", "revision": "C", "section": "Bearing Housing Bolt Torque"}],
    ))
    resp = assistant.ask("bearing housing bolt torque")
    assert resp.status == "answered"
    assert resp.review_id is None


def test_low_confidence_goes_to_review(assistant):
    assistant.llm = StubLLM(LLMAnswer(
        answer="Probably 52 N·m.", confidence="low",
        citations=[{"doc_id": "WI-101", "revision": "C", "section": "Bearing Housing Bolt Torque"}],
    ))
    assert assistant.ask("bearing housing bolt torque").status == "needs_review"


# ---------- human-in-the-loop ----------
def test_review_requires_named_reviewer_and_cannot_be_decided_twice(queue):
    rid = queue.submit("q", {"answer": "x"}, reason="test")
    with pytest.raises(ValueError):
        queue.decide(rid, True, reviewer="  ")
    assert queue.decide(rid, True, reviewer="Varun")["status"] == "approved"
    with pytest.raises(ValueError):
        queue.decide(rid, False, reviewer="Varun")


def test_audit_log_is_written(assistant):
    assistant.ask("Who can remove a lockout lock?")
    assert config.AUDIT_LOG.read_text().strip()
