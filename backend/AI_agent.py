# -*- coding: utf-8 -*-

import json
import os

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

from config import BASE_URL, MODEL, SYSTEM_MESSAGE
from memory import append_log_entries, trim_messages
from tools import TOOLS, call_tool
from vector_store import SearchResult
import vector_store


KNOWLEDGE_PREFLIGHT_PREFIX = "Knowledge base preflight result:"


def rewrite_query_with_history(client, messages, user_input):
    """
    Rewrite user query using conversation history for better retrieval.
    Example:
    - User1: "How to upload docs?"
    - User2: "How to delete?"
    - Rewritten: "How to delete an uploaded knowledge-base document?"
    """
    rewrite_prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are a query rewriting assistant. Given the conversation history and the current user question, "
                "rewrite the question to be clear, complete, and optimized for semantic search. "
                "Remove ambiguity, resolve pronouns (it, this, that, they) by referring to the actual topic, "
                "and make the question specific. Only return the rewritten question, nothing else."
            ),
        },
    ]
    
    # Add conversation history (exclude system message and knowledge preflight prefix)
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        
        # Skip system message and tool messages
        if role == "system" or role == "tool":
            continue
            
        # Clean up content by removing knowledge preflight prefix if present
        if content.startswith(KNOWLEDGE_PREFLIGHT_PREFIX):
            # Extract the original user question from the end
            lines = content.split("\n")
            user_question = ""
            found_user_question = False
            for line in lines:
                if line.strip() == "User question:":
                    found_user_question = True
                elif found_user_question:
                    user_question = line.strip()
                    break
            if user_question:
                content = user_question
        
        rewrite_prompt_messages.append({
            "role": role,
            "content": content,
        })
    
    # Add current user question
    rewrite_prompt_messages.append({
        "role": "user",
        "content": f"Current user question: {user_input}\n\nPlease rewrite this question clearly and completely:",
    })
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=rewrite_prompt_messages,
            temperature=0,
        )
        rewritten = response.choices[0].message.content.strip()
        return rewritten
    except Exception as error:
        print(f"Query rewrite failed, using original: {error}")
        return user_input


def rerank_with_llm(client, query, candidates, top_k=3):
    """
    两阶段检索的第二阶段：用 LLM 对召回结果进行重排序
    
    Args:
        client: OpenAI client
        query: 用户问题
        candidates: SearchResult 列表（第一阶段召回的结果）
        top_k: 最后返回的数量
    
    Returns:
        重排序后的 SearchResult 列表
    """
    if not candidates:
        return []
    
    # 如果候选数量已经小于等于 top_k，直接返回
    if len(candidates) <= top_k:
        return candidates
    
    # 构建重排序提示词
    rerank_prompt = f"""Task: Rank the following text snippets by their relevance to the question.

Question: {query}

Snippets:
"""
    
    for i, candidate in enumerate(candidates, 1):
        rerank_prompt += f"[{i}] (Score: {candidate.score:.3f})\n{candidate.text}\n\n"
    
    rerank_prompt += """
Please rank the snippets from MOST relevant to LEAST relevant to the question.
Only return a comma-separated list of numbers (e.g., "3,1,2,5,4").
Do not include any explanations or other text.
"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a relevance ranking assistant. You only output comma-separated numbers."},
                {"role": "user", "content": rerank_prompt}
            ],
            temperature=0,
        )
        
        ranking_text = response.choices[0].message.content.strip()
        
        # 解析排序结果
        try:
            # 尝试提取数字
            ranking = []
            for part in ranking_text.split(','):
                part = part.strip()
                if part.isdigit():
                    idx = int(part) - 1  # 转成 0-based
                    if 0 <= idx < len(candidates):
                        ranking.append(idx)
            
            # 如果解析成功，按新顺序排列
            if ranking:
                # 去重并只保留前 top_k 个
                seen = set()
                reranked = []
                for idx in ranking:
                    if idx not in seen and len(reranked) < top_k:
                        reranked.append(candidates[idx])
                        seen.add(idx)
                
                # 如果不够，用剩下的候选补充
                for i, candidate in enumerate(candidates):
                    if i not in seen and len(reranked) < top_k:
                        reranked.append(candidate)
                
                return reranked
        except Exception:
            pass
    
    except Exception as error:
        print(f"Rerank failed, using original ordering: {error}")
    
    # 如果重排序失败，返回原始 top_k
    return candidates[:top_k]


def build_user_message_with_knowledge_preflight(user_input, client=None, messages=None):
    return build_knowledge_preflight(user_input, client, messages)["content"]


def build_knowledge_preflight(user_input, client=None, messages=None):
    # --- 阶段 1: 查询重写（可选）---
    query_to_search = user_input
    if client and messages:
        query_to_search = rewrite_query_with_history(client, messages, user_input)
    
    # --- 阶段 2: 第一阶段 - 向量召回 ---
    # 先召回 15 个候选（粗筛）
    recall_k = 15
    final_top_k = 3
    min_score = 0.3
    
    try:
        # 使用混合检索（BM25 + 向量搜索）
        recall_results = vector_store.hybrid_search(query_to_search, top_k=recall_k, bm25_weight=0.3, vector_weight=0.7)
    except Exception as error:
        return {
            "content": (
                f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                f"search_knowledge error: {error}\n\n"
                "User question:\n"
                f"{user_input}"
            ),
            "sources": [],
        }
    
    # --- 阶段 3: 第二阶段 - 重排序（可选）---
    # 如果有 client 并且召回结果超过 final_top_k，就做重排序
    kept_results = recall_results
    if client and len(recall_results) > final_top_k:
        kept_results = rerank_with_llm(
            client,
            query_to_search,
            recall_results,
            top_k=final_top_k
        )
    else:
        # 没有 client 或结果不够，只按 min_score 过滤
        kept_results = [
            result for result in recall_results
            if result.score >= min_score
        ][:final_top_k]
    
    # --- 格式化结果（和 search_knowledge_with_sources 保持一致） ---
    if not kept_results:
        return {
            "content": (
                f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                f"No supported knowledge evidence was found for {query_to_search!r} "
                f"with score >= {min_score:.2f}. "
                "Tell the user the knowledge base does not contain enough evidence instead of guessing.\n\n"
                "User question:\n"
                f"{user_input}"
            ),
            "sources": [],
        }
    
    # 构建源信息
    sources = []
    lines = [
        (
            f"Knowledge evidence for {query_to_search!r}: {len(kept_results)} result(s). "
            "Before answering, verify that each snippet is actually about the user's question. "
            "Answer only from relevant snippets. Cite sources with their labels, such as [K1], only for claims directly supported by that snippet. "
            "If the snippets are unrelated or do not fully answer the question, say what is missing."
        ),
        "",
        "Sources:",
    ]
    
    for index, result in enumerate(kept_results, start=1):
        source_label = f"K{index}"
        sources.append({
            "label": source_label,
            "document_id": result.document_id,
            "chunk_id": getattr(result, "chunk_id", f"{result.document_id}_chunk_{result.chunk_index:04d}"),
            "chunk_index": result.chunk_index,
            "score": result.score,
            "text": result.text,
        })
        lines.extend([
            (
                f"[{source_label}] document_id={result.document_id} "
                f"chunk={result.chunk_index} score={result.score:.3f}"
            ),
            result.text,
            "",
        ])
    
    # 显示查询重写信息（如果有）
    rewritten_note = ""
    if query_to_search != user_input:
        rewritten_note = f"\n\n(Query was rewritten from: {user_input!r} to: {query_to_search!r} for better search results)"
    
    return {
        "content": (
            f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
            f"{chr(10).join(lines).rstrip()}{rewritten_note}\n\n"
            "User question:\n"
            f"{user_input}"
        ),
        "sources": sources,
        "original_query": user_input,
        "rewritten_query": query_to_search,
    }


def create_client():
    api_key = os.environ.get("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY. Please set it in .env.")

    return OpenAI(api_key=api_key, base_url=BASE_URL)


def format_model_error(error):
    if isinstance(error, AuthenticationError):
        return "Model request error: authentication failed. Check DEEPSEEK_API_KEY in .env."

    if isinstance(error, RateLimitError):
        return "Model request error: rate limit reached. Wait a moment and try again."

    if isinstance(error, BadRequestError):
        return f"Model request error: bad request. {error}"

    if isinstance(error, APIConnectionError):
        return f"Model request error: connection failed. {error}"

    if isinstance(error, APIStatusError):
        return f"Model request error: API returned status {error.status_code}. {error}"

    if isinstance(error, APIError):
        return f"Model request error: API error. {error}"

    return f"Model request error: {error}"


def format_tool_error(tool_name, error):
    if isinstance(error, json.JSONDecodeError):
        return f"{tool_name} error: tool arguments are not valid JSON."

    if isinstance(error, KeyError):
        return f"{tool_name} error: missing required argument {error}."

    if isinstance(error, TypeError):
        return f"{tool_name} error: invalid argument type. {error}"

    return f"{tool_name} error: {error}"


def confirm_tool_call(tool_name, tool_args):
    answer = input(f"Allow tool call {tool_name}({tool_args})? y/n: ").strip().lower()
    return answer in {"y", "yes"}


def run_tool_call(tool_call, remaining_file_read_lines, confirm_callback=confirm_tool_call):
    tool_name = tool_call.function.name
    raw_arguments = tool_call.function.arguments
    tool_args = raw_arguments
    denied_by_user = False

    try:
        tool_args = json.loads(raw_arguments)
        tool_result = call_tool(tool_name, tool_args)
    except Exception as error:
        tool_result = format_tool_error(tool_name, error)

    return tool_args, tool_result, remaining_file_read_lines, denied_by_user


def run_agent(client, messages, user_input, max_steps=5, knowledge_preflight=None, return_sources=False):
    new_messages = []
    remaining_file_read_lines = 0
    knowledge_preflight = knowledge_preflight or build_knowledge_preflight(user_input, client, messages)

    # Add this turn's user input with a deterministic knowledge-base preflight.
    user_message = {
        "role": "user",
        "content": knowledge_preflight["content"],
    }
    messages.append(user_message)
    new_messages.append(user_message)

    # Run a multi-step tool loop because later calls may depend on earlier results.
    for step in range(max_steps):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as error:
            error_message = {
                "role": "assistant",
                "content": format_model_error(error),
            }
            messages.append(error_message)
            new_messages.append(error_message)
            append_log_entries(new_messages)
            trim_messages(messages)
            if return_sources:
                return {
                    "answer": error_message["content"],
                    "sources": knowledge_preflight["sources"],
                }
            return error_message["content"]

        assistant_message = response.choices[0].message
        assistant_message_dict = assistant_message.model_dump(exclude_none=True)
        messages.append(assistant_message_dict)
        new_messages.append(assistant_message_dict)

        # No tool calls means the model has produced the final natural-language answer.
        if not assistant_message.tool_calls:
            append_log_entries(new_messages)
            trim_messages(messages)
            if return_sources:
                return {
                    "answer": assistant_message.content,
                    "sources": knowledge_preflight["sources"],
                }
            return assistant_message.content

        print(f"\nstep {step + 1}:")

        # One assistant response can request multiple tool calls.
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name

            tool_args, tool_result, remaining_file_read_lines, denied_by_user = run_tool_call(
                tool_call,
                remaining_file_read_lines,
                confirm_callback=confirm_tool_call,
            )
            print(f"tool call: {tool_name}({tool_args})")
            print(f"tool result: {tool_result}")

            # Bind the tool result to the specific tool call request.
            tool_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
            messages.append(tool_message)
            new_messages.append(tool_message)

    append_log_entries(new_messages)
    trim_messages(messages)
    stop_text = "The agent stopped because it used too many tool-calling steps."
    if return_sources:
        return {
            "answer": stop_text,
            "sources": knowledge_preflight["sources"],
        }
    return stop_text


def run_final_answer_stream(client, messages):
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tool_choice="none",
        temperature=0,
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield content


def run_agent_stream(client, messages, user_input, max_steps=5, knowledge_preflight=None):
    new_messages = []
    remaining_file_read_lines = 0
    knowledge_preflight = knowledge_preflight or build_knowledge_preflight(user_input, client, messages)

    user_message = {
        "role": "user",
        "content": knowledge_preflight["content"],
    }
    messages.append(user_message)
    new_messages.append(user_message)

    for step in range(max_steps):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as error:
            error_message = {
                "role": "assistant",
                "content": format_model_error(error),
            }
            messages.append(error_message)
            new_messages.append(error_message)
            append_log_entries(new_messages)
            trim_messages(messages)
            yield error_message["content"]
            return

        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            final_answer = []
            try:
                for content in run_final_answer_stream(client, messages):
                    final_answer.append(content)
                    yield content
            except Exception as error:
                error_text = format_model_error(error)
                final_answer.append(error_text)
                yield error_text

            assistant_message_dict = {
                "role": "assistant",
                "content": "".join(final_answer),
            }
            messages.append(assistant_message_dict)
            new_messages.append(assistant_message_dict)
            append_log_entries(new_messages)
            trim_messages(messages)
            return

        assistant_message_dict = assistant_message.model_dump(exclude_none=True)
        messages.append(assistant_message_dict)
        new_messages.append(assistant_message_dict)

        print(f"\nstep {step + 1}:")

        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name

            tool_args, tool_result, remaining_file_read_lines, denied_by_user = run_tool_call(
                tool_call,
                remaining_file_read_lines,
                confirm_callback=confirm_tool_call,
            )
            print(f"tool call: {tool_name}({tool_args})")
            print(f"tool result: {tool_result}")

            tool_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
            messages.append(tool_message)
            new_messages.append(tool_message)

    stop_message = {
        "role": "assistant",
        "content": "The agent stopped because it used too many tool-calling steps.",
    }
    messages.append(stop_message)
    new_messages.append(stop_message)
    append_log_entries(new_messages)
    trim_messages(messages)
    yield stop_message["content"]


def main():
    try:
        client = create_client()
    except RuntimeError as error:
        print(f"Startup error: {error}")
        return

    # The web app stores history in SQLite. The CLI starts a fresh local session.
    messages = [SYSTEM_MESSAGE.copy()]

    print("AI Agent started.")
    print("Try: what time is it now?")
    print("Try: search the knowledge base for deployment notes")
    print("Type q to quit.")

    while True:
        user_input = input("\nYou: ").strip()

        if user_input == "q":
            break

        answer = run_agent(client, messages, user_input)
        print(f"AI: {answer}")


if __name__ == "__main__":
    main()
