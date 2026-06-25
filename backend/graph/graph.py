import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

_CHECKPOINTER = None


def _get_checkpointer():
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        db_path = str(PROJECT_ROOT / "data" / "checkpoints.sqlite")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _CHECKPOINTER = SqliteSaver(sqlite3.connect(db_path))
    return _CHECKPOINTER

from chains.formatters import format_knowledge_preflight_payload
from chains.retrieval_chain import (
    resolve_retrieval_payload,
    retrieve_ranked_results,
)
from config import DEFAULT_KNOWLEDGE_MIN_SCORE, DEFAULT_KNOWLEDGE_TOP_K, MODEL, NO_EVIDENCE_ANSWER, PROJECT_ROOT, RECALL_K, STRICT_KNOWLEDGE_ABSTENTION
from graph.memory import extract_memories, format_memory_context, load_memories, save_memories
from graph.state import AgentState, trim_messages_by_token
from memory import append_log_entries
from model_client import format_model_error
from model_usage import record_model_usage
from app_logging import request_id_var


def should_abstain(knowledge_preflight):
    return STRICT_KNOWLEDGE_ABSTENTION and knowledge_preflight and not knowledge_preflight.get("sources")


def build_agent_graph(
    build_answer_response_chain,
    *,
    extract_text_content,
    knowledge_preflight_prefix,
    rerank_with_dashscope,
    system_message_content="",
    enable_checkpointer=False,
):
    _build_chain = build_answer_response_chain
    _extract = extract_text_content
    _prefix = knowledge_preflight_prefix
    _rerank = rerank_with_dashscope
    _system_msg = {"role": "system", "content": system_message_content}

    def init_messages(state: AgentState) -> AgentState:
        if state.get("messages"):
            return state
        messages = [_system_msg.copy()]
        if not state.get("_streaming_mode"):
            user_id = state.get("user_id")
            if user_id:
                memories = load_memories(user_id, limit=10)
                context = format_memory_context(memories)
                if context:
                    messages.append({"role": "system", "content": context})
        return {**state, "messages": messages}

    def check_evidence(state: AgentState) -> AgentState:
        return state

    def route_by_evidence(state: AgentState) -> str:
        if should_abstain(state.get("knowledge_preflight")):
            return "abstain"
        if state.get("knowledge_preflight") is not None:
            return "invoke_chain"
        return "resolve_query"

    def resolve_query(state: AgentState) -> AgentState:
        client = state["_client"]
        payload = {
            "user_input": state["user_input"],
            "messages": state.get("messages"),
            "top_k": DEFAULT_KNOWLEDGE_TOP_K,
            "min_score": DEFAULT_KNOWLEDGE_MIN_SCORE,
            "category": state.get("category"),
            "tags": state.get("tags"),
            "file_extensions": state.get("file_extensions"),
            "departments": state.get("departments"),
            "use_multi_query": state.get("use_multi_query"),
        }
        resolved = resolve_retrieval_payload(
            client,
            payload,
            extract_text_content=_extract,
            knowledge_preflight_prefix=_prefix,
        )
        return {
            **state,
            "query_to_search": resolved["query_to_search"],
            "queries_to_search": resolved["queries_to_search"],
        }

    def retrieve_documents(state: AgentState) -> AgentState:
        client = state["_client"]
        payload = {
            "user_input": state["user_input"],
            "messages": state.get("messages"),
            "query_to_search": state["query_to_search"],
            "queries_to_search": state["queries_to_search"],
            "top_k": DEFAULT_KNOWLEDGE_TOP_K,
            "min_score": DEFAULT_KNOWLEDGE_MIN_SCORE,
            "recall_k": RECALL_K,
            "category": state.get("category"),
            "tags": state.get("tags"),
            "file_extensions": state.get("file_extensions"),
            "departments": state.get("departments"),
        }
        result = retrieve_ranked_results(payload, rerank_with_dashscope=_rerank)
        return {
            **state,
            "kept_results": result["kept_results"],
            "access_stats": result.get("access_stats", {}),
        }

    def format_evidence(state: AgentState) -> AgentState:
        payload = {
            "user_input": state["user_input"],
            "query_to_search": state["query_to_search"],
            "min_score": DEFAULT_KNOWLEDGE_MIN_SCORE,
            "kept_results": state.get("kept_results", []),
            "access_stats": state.get("access_stats", {}),
        }
        formatted = format_knowledge_preflight_payload(
            payload,
            knowledge_preflight_prefix=_prefix,
        )
        return {
            **state,
            "knowledge_preflight": formatted,
            "sources": formatted.get("sources", []),
            "_route": "run_rag",
        }

    def route_after_format(state: AgentState) -> str:
        if state.get("_streaming_mode"):
            return "end"
        return "invoke_chain"

    def noop_end(state: AgentState) -> AgentState:
        return state

    def invoke_chain(state: AgentState) -> AgentState:
        client = state["_client"]
        messages = state["messages"]
        user_input = state["user_input"]
        knowledge_preflight = state.get("knowledge_preflight")

        chain = _build_chain(client)
        try:
            chain_result = chain.invoke({
                "messages": messages,
                "user_input": user_input,
                "knowledge_preflight": knowledge_preflight,
            })
            kp = chain_result["knowledge_preflight"]
            return {
                **state,
                "_chain_ok": True,
                "answer": chain_result["answer"],
                "sources": kp.get("sources", []),
                "knowledge_preflight": kp,
            }
        except Exception as error:
            return {
                **state,
                "_chain_ok": False,
                "answer": format_model_error(error),
                "sources": state.get("sources", []),
            }

    def route_by_chain_result(state: AgentState) -> str:
        return "record_usage" if state.get("_chain_ok") else "handle_error"

    def record_usage(state: AgentState) -> AgentState:
        messages = state["messages"]
        knowledge_preflight = state.get("knowledge_preflight") or {}
        record_model_usage(
            provider="deepseek",
            model=MODEL,
            operation="chat",
            request_id=request_id_var.get(),
            input_texts=[m.get("content", "") for m in messages] + [state["user_input"]],
            output_texts=[state["answer"]],
            document_count=len(knowledge_preflight.get("sources") or []),
        )
        return state

    def append_messages(state: AgentState) -> AgentState:
        messages = state["messages"]
        knowledge_preflight = state["knowledge_preflight"]
        user_msg = {"role": "user", "content": knowledge_preflight["content"]}
        assistant_msg = {"role": "assistant", "content": state["answer"]}
        messages.append(user_msg)
        messages.append(assistant_msg)
        append_log_entries([user_msg, assistant_msg])
        return state

    def trim_history(state: AgentState) -> AgentState:
        state["messages"] = trim_messages_by_token(state.get("messages", []))
        return {**state, "_route": "run_rag"}

    def extract_memories_node(state: AgentState) -> AgentState:
        if state.get("_streaming_mode"):
            return state
        user_id = state.get("user_id")
        if not user_id:
            return state
        messages = state.get("messages", [])
        if len(messages) < 2:
            return state
        client = state.get("_client")
        if not client:
            return state
        counter = state.get("_extraction_counter", 0) + 1
        state["_extraction_counter"] = counter
        if counter < 5:
            return state
        state["_extraction_counter"] = 0
        assistant_msg = messages[-1].get("content", "")
        user_msg = messages[-2].get("content", "")
        facts = extract_memories(client, user_msg, assistant_msg)
        if facts:
            save_memories(user_id, facts)
        return state

    def handle_error(state: AgentState) -> AgentState:
        messages = state["messages"]
        error_msg = {"role": "assistant", "content": state["answer"]}
        messages.append(error_msg)
        append_log_entries([error_msg])
        state["messages"] = trim_messages_by_token(messages)
        return {**state, "_route": "error"}

    def abstain(state: AgentState) -> AgentState:
        return {
            **state,
            "answer": NO_EVIDENCE_ANSWER,
            "sources": [],
        }

    def append_abstain_message(state: AgentState) -> AgentState:
        messages = state["messages"]
        knowledge_preflight = state.get("knowledge_preflight")
        if knowledge_preflight:
            user_msg = {"role": "user", "content": knowledge_preflight["content"]}
            assistant_msg = {"role": "assistant", "content": state["answer"]}
            messages.append(user_msg)
            messages.append(assistant_msg)
            append_log_entries([user_msg, assistant_msg])
            state["messages"] = trim_messages_by_token(messages)
        return {**state, "_route": "abstain"}

    workflow = StateGraph(AgentState)
    workflow.add_node("init_messages", init_messages)
    workflow.add_node("check_evidence", check_evidence)
    workflow.add_node("resolve_query", resolve_query)
    workflow.add_node("retrieve_documents", retrieve_documents)
    workflow.add_node("format_evidence", format_evidence)
    workflow.add_node("invoke_chain", invoke_chain)
    workflow.add_node("record_usage", record_usage)
    workflow.add_node("append_messages", append_messages)
    workflow.add_node("trim_history", trim_history)
    workflow.add_node("extract_memories_node", extract_memories_node)
    workflow.add_node("handle_error", handle_error)
    workflow.add_node("abstain", abstain)
    workflow.add_node("append_abstain_message", append_abstain_message)
    workflow.add_node("noop_end", noop_end)

    workflow.add_conditional_edges(
        "check_evidence",
        route_by_evidence,
        {"abstain": "abstain", "invoke_chain": "invoke_chain", "resolve_query": "resolve_query"},
    )
    workflow.add_edge("resolve_query", "retrieve_documents")
    workflow.add_edge("retrieve_documents", "format_evidence")
    workflow.add_conditional_edges(
        "format_evidence",
        route_after_format,
        {"invoke_chain": "invoke_chain", "end": "noop_end"},
    )
    workflow.add_conditional_edges(
        "invoke_chain",
        route_by_chain_result,
        {"record_usage": "record_usage", "handle_error": "handle_error"},
    )
    workflow.add_edge("record_usage", "append_messages")
    workflow.add_edge("append_messages", "trim_history")
    workflow.add_edge("trim_history", "extract_memories_node")
    workflow.add_edge("extract_memories_node", END)
    workflow.add_edge("handle_error", END)
    workflow.add_edge("abstain", "append_abstain_message")
    workflow.add_edge("append_abstain_message", "extract_memories_node")
    workflow.add_edge("noop_end", END)

    workflow.set_entry_point("init_messages")
    workflow.add_edge("init_messages", "check_evidence")

    cp = _get_checkpointer() if enable_checkpointer else None
    return workflow.compile(checkpointer=cp)


def build_answer_stream_graph(
    build_answer_context_chain,
    build_prepared_answer_text_chain,
):
    _context_builder = build_answer_context_chain
    _answer_builder = build_prepared_answer_text_chain

    def stream_answer(state: AgentState) -> AgentState:
        from langgraph.config import dispatch_custom_event

        client = state["_client"]
        knowledge_preflight = state.get("knowledge_preflight")
        messages = state["messages"]
        user_input = state["user_input"]

        context_chain = _context_builder(client)
        answer_chain = _answer_builder(client)

        try:
            prepared_payload = context_chain.invoke({
                "messages": messages,
                "user_input": user_input,
                "knowledge_preflight": knowledge_preflight,
            })
        except Exception as error:
            error_text = format_model_error(error)
            dispatch_custom_event("token", error_text)
            return {**state, "answer": error_text, "_route": "error"}

        user_msg = {"role": "user", "content": prepared_payload["knowledge_preflight"]["content"]}
        messages.append(user_msg)

        final_answer = []
        try:
            for token in answer_chain.stream(prepared_payload):
                final_answer.append(token)
                dispatch_custom_event("token", token)
        except Exception as error:
            error_text = format_model_error(error)
            final_answer.append(error_text)
            dispatch_custom_event("token", error_text)

        full_answer = "".join(final_answer)
        record_model_usage(
            provider="deepseek",
            model=MODEL,
            operation="chat_stream",
            request_id=request_id_var.get(),
            input_texts=[m.get("content", "") for m in messages] + [user_input],
            output_texts=[full_answer],
            document_count=len(prepared_payload.get("knowledge_preflight", {}).get("sources") or []),
        )

        assistant_msg = {"role": "assistant", "content": full_answer}
        messages.append(assistant_msg)
        append_log_entries([user_msg, assistant_msg])
        trim_messages(messages)

        return {**state, "answer": full_answer, "_route": "streamed"}

    workflow = StateGraph(AgentState)
    workflow.add_node("stream_answer", stream_answer)
    workflow.set_entry_point("stream_answer")
    workflow.add_edge("stream_answer", END)
    return workflow.compile()
