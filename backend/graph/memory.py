import hashlib
import json
import sqlite3
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langgraph.store.sqlite import SqliteStore

from config import PROJECT_ROOT

_STORE = None


def _get_store():
    global _STORE
    if _STORE is None:
        db_path = str(PROJECT_ROOT / "data" / "memories.sqlite")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _STORE = SqliteStore(sqlite3.connect(db_path))
    return _STORE


MEMORY_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "Extract factual statements about the user from the conversation below.\n"
            "Each statement must be a single, atomic fact.\n"
            "Focus on: user preferences, user's project or work details, "
            "user's decisions, user's requirements or constraints.\n"
            "Ignore generic greetings, polite exchanges, confirmations, "
            "and trivial acknowledgements that contain no substantive information.\n"
            "Return ONLY a JSON list of strings, no other text.\n"
            "Example: [\"User prefers concise answers\", \"User is working on a RAG project\"]"
        ),
    ),
    ("human", "Conversation:\n{conversation}"),
])


def extract_memories(client, user_msg, assistant_msg):
    conversation = f"User: {user_msg}\n\nAssistant: {assistant_msg}"
    try:
        prompt = MEMORY_EXTRACTION_PROMPT.format_messages(conversation=conversation)
        response = client.invoke(prompt, temperature=0)
        content = getattr(response, "content", "") or ""
        facts = json.loads(content)
        if isinstance(facts, list):
            return [str(fact).strip() for fact in facts if fact and str(fact).strip()]
        return []
    except Exception:
        return []


def _fact_key(fact):
    return hashlib.md5(fact.encode("utf-8")).hexdigest()


def save_memories(user_id, facts):
    if not facts:
        return
    store = _get_store()
    namespace = ("user", str(user_id), "facts")
    existing = {item.value.get("content", "") for item in store.search(namespace, limit=50)}
    for fact in facts:
        normalized = fact.strip().rstrip("。.")
        if any(normalized in e or e in normalized for e in existing):
            continue
        key = _fact_key(fact)
        store.put(namespace, key, {"content": fact})


def load_memories(user_id, limit=10):
    store = _get_store()
    namespace = ("user", str(user_id), "facts")
    items = store.search(namespace, limit=limit)
    return [item.value.get("content", "") for item in items]


def format_memory_context(memories):
    if not memories:
        return ""
    lines = ["\nKnown facts about the user:"]
    for memory in memories:
        lines.append(f"- {memory}")
    return "\n".join(lines)
