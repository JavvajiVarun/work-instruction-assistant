"""MCP server: exposes the assistant as tools any MCP client (e.g. Claude Desktop) can call.

Read-only by design: the AI can search and read approved documents, but there is
NO tool that edits documents or approves reviews. Approval stays with a human.

Run (stdio):  python -m wia.mcp_server
"""
import logging
import os
import sys

try:  # MCP Python SDK v2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # MCP Python SDK v1
    from mcp.server.fastmcp import FastMCP as _Server

from .assistant import Assistant
from .llm import ClaudeLLM, FakeLLM

# MCP stdio uses stdout for protocol messages, so logs must go to stderr.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = _Server("work-instruction-assistant")
_assistant = Assistant(llm=FakeLLM() if os.getenv("WIA_OFFLINE") == "1" else ClaudeLLM())


@mcp.tool()
def search_work_instructions(query: str, k: int = 4) -> list[dict]:
    """Search APPROVED, latest-revision work instructions. Returns matching sections with doc_id, revision and score."""
    k = max(1, min(k, 10))
    return [c.model_dump() for c in _assistant.search(query, k)]


@mcp.tool()
def get_work_instruction(doc_id: str) -> dict:
    """Get the full current approved revision of a work instruction by doc_id (e.g. 'WI-101')."""
    doc = _assistant.get_document(doc_id)
    if doc is None:
        return {"error": f"{doc_id} not found among approved documents"}
    return doc


@mcp.tool()
def ask_work_instructions(question: str) -> dict:
    """Ask a question. Returns a grounded answer with citations; uncertain answers are queued for human review."""
    return _assistant.ask(question, user="mcp-client").model_dump()


if __name__ == "__main__":
    mcp.run()
