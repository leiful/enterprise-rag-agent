import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from AI_agent import (
    KNOWLEDGE_PREFLIGHT_PREFIX,
    build_user_message_with_knowledge_preflight,
    main,
    run_agent,
    run_agent_stream,
    run_tool_call,
)
from config import SYSTEM_MESSAGE


def knowledge_preflight(text="No supported knowledge evidence was found.", sources=None):
    return {
        "content": (
            f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
            f"{text}\n\n"
            "User question:\n"
            "patched question"
        ),
        "sources": sources or [],
    }


def make_tool_call(name, arguments):
    return SimpleNamespace(
        id=f"call_{name}",
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def make_message(content="", tool_calls=None):
    tool_calls = tool_calls or []

    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda exclude_none=True: {
            "role": "assistant",
            "content": content,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        },
    )


def make_response(message):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=message),
        ],
    )


def make_stream_chunk(content):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(delta=SimpleNamespace(content=content)),
        ],
    )


class RunToolCallTests(unittest.TestCase):
    def test_get_time_returns_result(self):
        tool_call = make_tool_call("get_time", "{}")

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, {})
        self.assertRegex(tool_result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)

    def test_invalid_json_returns_clear_error(self):
        tool_call = make_tool_call("get_time", "{bad json")

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, "{bad json")
        self.assertEqual(
            tool_result,
            "get_time error: tool arguments are not valid JSON.",
        )
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)

    def test_missing_required_argument_returns_clear_error(self):
        tool_call = make_tool_call("search_knowledge", "{}")

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, {})
        self.assertEqual(
            tool_result,
            "search_knowledge error: missing required argument 'query'.",
        )
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)


class RunAgentTests(unittest.TestCase):
    def test_build_user_message_with_knowledge_preflight(self):
        with patch(
            "AI_agent.build_knowledge_preflight",
            return_value={
                "content": (
                    f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                    "No supported knowledge evidence was found.\n\n"
                    "User question:\n"
                    "who is trump?"
                ),
                "sources": [],
            },
        ):
            message = build_user_message_with_knowledge_preflight("who is trump?")

        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, message)
        self.assertIn("No supported knowledge evidence was found.", message)
        self.assertIn("User question:\nwho is trump?", message)

    def test_run_agent_uses_tool_result_then_returns_answer(self):
        first_message = make_message(
            tool_calls=[
                make_tool_call("get_time", "{}"),
            ],
        )
        second_message = make_message(content="The current time was checked.")
        calls = [make_response(first_message), make_response(second_message)]
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: calls.pop(0),
                ),
            ),
        )
        messages = [{"role": "system", "content": "test"}]

        with patch(
            "AI_agent.build_knowledge_preflight",
            return_value={
                "content": (
                    f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                    "No supported knowledge evidence was found.\n\n"
                    "User question:\n"
                    "what time is it?"
                ),
                "sources": [],
            },
        ):
            with patch("AI_agent.append_log_entries"):
                with redirect_stdout(StringIO()):
                    answer = run_agent(client, messages, "what time is it?")

        self.assertEqual(answer, "The current time was checked.")
        self.assertEqual(len(calls), 0)
        self.assertTrue(any(message.get("role") == "tool" for message in messages))
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, messages[1]["content"])
        self.assertIn("User question:\nwhat time is it?", messages[1]["content"])

    def test_run_agent_preflights_ordinary_questions_before_model_call(self):
        first_message = make_message(content="Knowledge base has no evidence. Trump is...")
        captured_messages = []

        def create_completion(**kwargs):
            captured_messages.append(kwargs["messages"])
            return make_response(first_message)

        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=create_completion,
                ),
            ),
        )
        messages = [{"role": "system", "content": "test"}]

        with patch(
            "AI_agent.build_knowledge_preflight",
            return_value={
                "content": (
                    f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                    "No supported knowledge evidence was found.\n\n"
                    "User question:\n"
                    "who is trump?"
                ),
                "sources": [],
            },
        ):
            with redirect_stdout(StringIO()):
                with patch("AI_agent.append_log_entries"):
                    answer = run_agent(client, messages, "who is trump?")

        self.assertEqual(answer, "Knowledge base has no evidence. Trump is...")
        self.assertEqual(len(captured_messages), 1)
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, captured_messages[0][1]["content"])
        self.assertIn("User question:\nwho is trump?", captured_messages[0][1]["content"])

    def test_run_agent_stream_streams_final_answer_after_tool_check(self):
        first_message = make_message(content="Draft answer")
        calls = [make_response(first_message)]
        stream_chunks = [
            make_stream_chunk("hello "),
            make_stream_chunk("there"),
        ]

        def create_completion(**kwargs):
            if kwargs.get("stream"):
                return iter(stream_chunks)

            return calls.pop(0)

        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=create_completion,
                ),
            ),
        )
        messages = [{"role": "system", "content": "test"}]

        with patch(
            "AI_agent.build_knowledge_preflight",
            return_value={
                "content": (
                    f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                    "No supported knowledge evidence was found.\n\n"
                    "User question:\n"
                    "hello"
                ),
                "sources": [],
            },
        ):
            with patch("AI_agent.append_log_entries"):
                answer = "".join(run_agent_stream(client, messages, "hello"))

        self.assertEqual(answer, "hello there")
        self.assertEqual(messages[-1], {"role": "assistant", "content": "hello there"})
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, messages[1]["content"])


class MainTests(unittest.TestCase):
    def test_main_prints_startup_error_when_api_key_is_missing(self):
        output = StringIO()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            with redirect_stdout(output):
                main()

        self.assertIn(
            "Startup error: Missing DEEPSEEK_API_KEY. Please set it in .env.",
            output.getvalue(),
        )


class SystemMessageTests(unittest.TestCase):
    def test_system_message_requires_cited_knowledge_answers(self):
        content = SYSTEM_MESSAGE["content"]

        self.assertIn("Every user message includes a Knowledge base preflight result", content)
        self.assertIn("begin by saying the knowledge base does not contain enough relevant evidence", content)
        self.assertIn("Only cite the provided source labels such as [K1]", content)
        self.assertIn("Do not add unsupported details", content)


if __name__ == "__main__":
    unittest.main()
