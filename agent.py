"""
Simple LangGraph ReAct-style ArXiv agent.

Usage:
  # Local dev (requires langgraph CLI):
  langgraph dev agent.py::make_arxiv_agent

Factory required by langgraph.json: `make_arxiv_agent()` returns a compiled graph app.
"""
from typing import Annotated, List

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver

# LLM + tools
from langchain_openai import ChatOpenAI
from langchain_community.retrievers import ArxivRetriever
from langchain_core.tools import tool


class AgentState(MessagesState):
    """Extend MessagesState to persist chat history and trends."""

    trends: Annotated[List[str], "add"]


@tool
def search_arxiv_trends(query: str, num_results: int = 5) -> str:
    """Search ArXiv for latest papers on a topic and return brief summaries.

    The `ArxivRetriever` used here is the community retriever from
    `langchain_community`. In some installations the exact class name may
    vary; adapt imports if needed.
    """
    retriever = ArxivRetriever.load()
    docs = retriever.invoke(query, num_results=num_results)

    out_lines = []
    for d in docs:
        meta = d.metadata or {}
        title = meta.get("Title") or meta.get("title") or "N/A"
        snippet = (d.page_content or "")[:200]
        out_lines.append(f"{title}: {snippet}...")

    return "\n\n".join(out_lines)


# Bind tools to the LLM so the model can call them.
llm = ChatOpenAI(model="gpt-4o-mini")
try:
    llm = llm.bind_tools([search_arxiv_trends])
except Exception:
    # Some runtimes may not require explicit binding; keep compatibility.
    pass


def agent_node(state: AgentState):
    """Single graph node: run the LLM on accumulated messages and return an update.

    This is intentionally simple: a real ReAct agent would parse LLM outputs
    to detect tool calls and route them to tools; many LangGraph/LangChain
    helpers exist to implement full ReAct behaviour — adapt as needed.
    """
    messages = state.get("messages", [])

    # Call LLM with the conversation messages. Return value may be a string
    # or a structured message depending on your LLM wrapper.
    result = llm.invoke(messages)

    # Append result to messages and return new state fragment
    return {
        "messages": messages + [result],
    }


# Build the workflow graph with a memory checkpointer for local dev.
workflow = StateGraph(state_schema=AgentState)
workflow.add_node("agent", agent_node)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)

checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer)


# Factory used by langgraph.json and the CLI.
def make_arxiv_agent():
    return app


if __name__ == "__main__":
    print("Module loaded. Run `langgraph dev agent.py::make_arxiv_agent` to start local dev.")
