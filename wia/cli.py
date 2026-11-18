"""Command line interface.

  python -m wia.cli ask "What torque for the pump bearing housing bolts?"
  python -m wia.cli ask --offline "..."          # no API key needed
  python -m wia.cli docs                          # what's indexed vs excluded
  python -m wia.cli reviews                       # pending human reviews
  python -m wia.cli approve 1 --reviewer "Varun"  # or: reject 1 --reviewer ...
"""
import argparse
import json
import logging

from .assistant import Assistant
from .documents import load_all
from .llm import ClaudeLLM, FakeLLM
from .review import ReviewQueue
from . import config


def main() -> None:
    p = argparse.ArgumentParser(prog="wia")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask"); a.add_argument("question"); a.add_argument("--offline", action="store_true")
    sub.add_parser("docs")
    r = sub.add_parser("reviews"); r.add_argument("--all", action="store_true")
    for name in ("approve", "reject"):
        d = sub.add_parser(name); d.add_argument("review_id", type=int)
        d.add_argument("--reviewer", required=True); d.add_argument("--comment", default="")

    args = p.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    if args.cmd == "ask":
        assistant = Assistant(llm=FakeLLM() if args.offline else ClaudeLLM())
        print(json.dumps(assistant.ask(args.question, user="cli").model_dump(), indent=2))
    elif args.cmd == "docs":
        from .documents import controlled_set
        all_docs = load_all(config.DOCS_DIR)
        indexed = {(d["doc_id"], d["revision"]) for d in controlled_set(all_docs)}
        for d in all_docs:
            flag = "INDEXED " if (d["doc_id"], d["revision"]) in indexed else "excluded"
            print(f"{flag}  {d['doc_id']:<7} rev {d['revision']:<2} {d['status']:<11} {d['title']}")
    elif args.cmd == "reviews":
        print(json.dumps(ReviewQueue().list(None if args.all else "pending"), indent=2))
    else:
        print(json.dumps(ReviewQueue().decide(args.review_id, args.cmd == "approve", args.reviewer, args.comment), indent=2))


if __name__ == "__main__":
    main()
