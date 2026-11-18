# Work Instruction Assistant (MVP)

An AI assistant that helps technicians find answers in **controlled work instructions**, with
**citations, revision control, refusals, human review, and an audit trail**.

> Status: MVP built as a learning project. Sample documents describe a **fictional** facility.

## What it does

A technician asks: *"What torque should I use on the pump bearing housing bolts?"*

```json
{
  "answer": "Torque to 52 N·m in a star pattern, in two passes (50% then 100%).",
  "citations": [{"doc_id": "WI-101", "revision": "C", "section": "Bearing Housing Bolt Torque"}],
  "confidence": "high",
  "status": "answered"
}
```

Note: an older **Rev B** says 45 N·m. The assistant never sees it, because only the
**latest approved revision** is indexed. Drafts are excluded too.

## How it works

```
question
   │
 [1] Retrieve top-k sections (TF-IDF) from APPROVED, LATEST-revision docs only
   │
 [2] Best score too low? ──► refuse: "not in approved documents" (no LLM call)
   │
 [3] Claude answers with forced structured output (JSON schema via tool use)
   │
 [4] Check citations: each cited doc+revision must be one we actually retrieved
   │
 [5] Low confidence or bad citation? ──► human review queue (named approver required)
   │
 [6] Everything written to an append-only audit log
```

| Requirement | How it's handled |
|---|---|
| Configuration control | Only `status: approved`, latest revision per `doc_id` is indexed |
| Source traceability | Every answer cites doc_id + revision + section |
| No guessing | Low retrieval score → refuse; model must flag `insufficient_information` |
| Hallucination check | Citations not in retrieved sources are dropped and sent to review |
| Human in the loop | Review queue; approve/reject needs a named reviewer; can't be decided twice |
| Observability | `data/audit.jsonl` logs every question, status, sources and decision |
| Integration | REST API (FastAPI) + MCP server (read-only tools) + CLI |
| Testing & evaluation | `pytest` unit tests + eval set with retrieval and refusal metrics |

## Project layout

```
wia/
  documents.py   load docs, front matter, revision filter, section chunks
  retriever.py   TF-IDF retrieval (swap for a vector DB later)
  llm.py         Claude call with forced JSON schema output; FakeLLM for offline/tests
  assistant.py   the pipeline and guardrails
  review.py      SQLite review queue + JSONL audit log
  api.py         FastAPI endpoints
  mcp_server.py  MCP tools: search / get document / ask (no write tools on purpose)
  cli.py         command line
data/docs/       sample work instructions (Markdown + YAML front matter)
eval/            question set + evaluation script
tests/           unit tests (no API key needed)
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                                   # 10 tests, no API key needed
python -m wia.cli docs                      # see what's indexed vs excluded
python eval/run_eval.py --retrieval-only    # free retrieval + refusal eval
python -m wia.cli ask --offline "Who can remove a lockout lock?"   # no key needed

cp .env.example .env                        # add your ANTHROPIC_API_KEY
python -m wia.cli ask "What torque for the pump bearing housing bolts?"
python eval/run_eval.py                     # full end-to-end eval with Claude

uvicorn wia.api:app --reload                # then open http://localhost:8000/docs
python -m wia.cli reviews                   # pending human reviews
python -m wia.cli approve 1 --reviewer "Varun" --comment "Checked against WI-101 Rev C"
```

### Use it from Claude Desktop (MCP)

Add to `claude_desktop_config.json` (use your own absolute paths):

```json
{
  "mcpServers": {
    "work-instructions": {
      "command": "/ABSOLUTE/PATH/work-instruction-assistant/.venv/bin/python",
      "args": ["-m", "wia.mcp_server"],
      "cwd": "/ABSOLUTE/PATH/work-instruction-assistant",
      "env": {"WIA_OFFLINE": "1"}
    }
  }
}
```

`WIA_OFFLINE=1` lets Claude Desktop use the search and get-document tools without a second API key.

## Results so far

Retrieval-only eval (13 questions: 10 answerable, 3 unanswerable):

| Metric | Result |
|---|---|
| Retrieval hit@4 (right doc + revision found) | 10/10 |
| Correct refusal by score threshold alone | 2/3 |

**Finding:** "What belt deflection should I set on cooling fan F-10?" only exists in a *draft*
doc. The draft is correctly excluded, but the word "set" matched another doc above the score
threshold. So the threshold alone isn't enough. In full mode the model's
`insufficient_information` flag is the second safety layer. Run `python eval/run_eval.py` to
measure that end to end.

## Known limitations / next steps

- TF-IDF matches words, not meaning. Next: embeddings + a vector DB (Chroma / pgvector), hybrid search.
- Revision compare is simple string order (A < B < C). Real systems should take revision state from PLM/document control.
- Markdown only. Next: PDF ingestion with page numbers in citations.
- No authentication or role-based access yet.
- Add tracing (e.g. OpenTelemetry) and a small review UI.
