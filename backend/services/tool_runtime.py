# -*- coding: utf-8 -*-

import json

from pydantic import ValidationError

from tools import get_langchain_tool_map


def get_tool_call_name(tool_call):
    if isinstance(tool_call, dict):
        return tool_call.get("name", "")
    return tool_call.function.name


def format_tool_error(tool_name, error):
    if isinstance(error, ValidationError):
        details = error.errors()
        if details:
            first_error = details[0]
            location = first_error.get("loc") or []
            missing_name = location[-1] if location else "unknown"
            if first_error.get("type") == "missing":
                return f"{tool_name} error: missing required argument {missing_name!r}."
        return f"{tool_name} error: invalid arguments. {error}"

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
    denied_by_user = False
    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
    try:
        tool_name = get_tool_call_name(tool_call)
        tool = get_langchain_tool_map()[tool_name]
        tool_result = tool.invoke(tool_args)
    except Exception as error:
        tool_name = get_tool_call_name(tool_call)
        tool_result = format_tool_error(tool_name, error)
    return tool_args, tool_result, remaining_file_read_lines, denied_by_user
