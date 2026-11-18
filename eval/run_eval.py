"""Evaluate the assistant against a fixed question set.

  python eval/run_eval.py --retrieval-only   # free, no API key: tests retrieval + refusal
  python eval/run_eval.py                    # full end-to-end with Claude

Metrics
  retrieval_hit@k      expected doc+revision appears in the top-k retrieved chunks
  correct_refusal      unanswerable questions were refused (not answered)
  answer_contains      answer includes the key fact(s) (full mode only)
  citation_correct     answer cites the expected doc+revision (full mode only)
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wia.assistant import Assistant  # noqa: E402
from wia.llm import ClaudeLLM, FakeLLM  # noqa: E402
from wia.review import ReviewQueue  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--retrieval-only", action="store_true")
    args = p.parse_args()

    questions = [json.loads(l) for l in (Path(__file__).parent / "questions.jsonl").read_text().splitlines() if l.strip()]
    tmp = Path(tempfile.mkdtemp())
    assistant = Assistant(
        llm=FakeLLM() if args.retrieval_only else ClaudeLLM(),
        review_queue=ReviewQueue(tmp / "eval.db"),
    )

    totals = {"retrieval_hit": [0, 0], "correct_refusal": [0, 0], "answer_contains": [0, 0], "citation_correct": [0, 0]}
    rows = []
    for q in questions:
        retrieved = assistant.search(q["question"])
        top_ok = bool(retrieved) and retrieved[0].score >= assistant.min_score
        row = {"id": q["id"]}

        if q["answerable"]:
            hit = any(c.doc_id == q["expected_doc"] and c.revision == q["expected_revision"] for c in retrieved)
            totals["retrieval_hit"][0] += hit; totals["retrieval_hit"][1] += 1
            row["retrieval_hit"] = hit

        if args.retrieval_only:
            if not q["answerable"]:
                refused = not top_ok
                totals["correct_refusal"][0] += refused; totals["correct_refusal"][1] += 1
                row["refused"] = refused
        else:
            resp = assistant.ask(q["question"], user="eval")
            row["status"] = resp.status
            if q["answerable"]:
                contains = all(s.lower() in resp.answer.lower() for s in q["must_contain"])
                cited = any(c.doc_id == q["expected_doc"] and c.revision == q["expected_revision"] for c in resp.citations)
                totals["answer_contains"][0] += contains; totals["answer_contains"][1] += 1
                totals["citation_correct"][0] += cited; totals["citation_correct"][1] += 1
                row.update(answer_contains=contains, citation_correct=cited)
            else:
                refused = resp.status == "refused"
                totals["correct_refusal"][0] += refused; totals["correct_refusal"][1] += 1
                row["refused"] = refused
        rows.append(row)

    for r in rows:
        print(r)
    print("\n=== Summary ===")
    for name, (ok, n) in totals.items():
        if n:
            print(f"{name:<18} {ok}/{n}  ({ok / n:.0%})")


if __name__ == "__main__":
    main()
