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

from config import BASE_URL, MAX_FILE_READ_LINES_PER_TURN, MODEL
from memory import append_log_entries, load_messages, save_messages, trim_messages
from tools import TOOLS, call_tool


REQUIRES_CONFIRMATION = {"write_file", "replace_in_file", "delete_file"}


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

        if tool_name in REQUIRES_CONFIRMATION:
            if not confirm_callback(tool_name, tool_args):
                denied_by_user = True
                return (
                    tool_args,
                    f"{tool_name} denied by user. Do not try another file modification tool for this request.",
                    remaining_file_read_lines,
                    denied_by_user,
                )

        if tool_name == "read_file":
            if remaining_file_read_lines <= 0:
                tool_result = (
                    "read_file error: per-turn file read limit reached. "
                    "Ask to continue in the next message."
                )
            elif "path" not in tool_args:
                tool_result = call_tool(tool_name, tool_args)
            else:
                requested_lines = tool_args.get("max_lines", remaining_file_read_lines)
                allowed_lines = min(requested_lines, remaining_file_read_lines)
                tool_args["max_lines"] = allowed_lines
                remaining_file_read_lines -= allowed_lines
                tool_result = call_tool(tool_name, tool_args)
        else:
            tool_result = call_tool(tool_name, tool_args)
    except Exception as error:
        tool_result = format_tool_error(tool_name, error)

    return tool_args, tool_result, remaining_file_read_lines, denied_by_user


def run_agent(client, messages, user_input, max_steps=5):
    new_messages = []
    remaining_file_read_lines = MAX_FILE_READ_LINES_PER_TURN

    # Add this turn's user input to the shared message history.
    user_message = {"role": "user", "content": user_input}
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
            return error_message["content"]

        assistant_message = response.choices[0].message
        assistant_message_dict = assistant_message.model_dump(exclude_none=True)
        messages.append(assistant_message_dict)
        new_messages.append(assistant_message_dict)

        # No tool calls means the model has produced the final natural-language answer.
        if not assistant_message.tool_calls:
            append_log_entries(new_messages)
            trim_messages(messages)
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

            if denied_by_user:
                denied_message = {
                    "role": "assistant",
                    "content": (
                        "File modification was cancelled. No other write, edit, or delete tool was attempted."
                    ),
                }
                messages.append(denied_message)
                new_messages.append(denied_message)
                append_log_entries(new_messages)
                trim_messages(messages)
                return denied_message["content"]

    append_log_entries(new_messages)
    trim_messages(messages)
    return "The agent stopped because it used too many tool-calling steps."


def main():
    try:
        client = create_client()
    except RuntimeError as error:
        print(f"Startup error: {error}")
        return

    # Restore short-term memory from the JSON history file.
    messages = load_messages()

    print("AI Agent started.")
    print("Try: what time is it now?")
    print("Try: list project files")
    print("Type q to quit.")

    while True:
        user_input = input("\nYou: ").strip()

        if user_input == "q":
            break

        answer = run_agent(client, messages, user_input)
        save_messages(messages)
        print(f"AI: {answer}")


if __name__ == "__main__":
    main()
