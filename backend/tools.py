# -*- coding: utf-8 -*-

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import (
    ALLOWED_READ_EXTENSIONS,
    EXCLUDED_READ_FILES,
    MAX_PROJECT_SEARCH_MATCHES,
    MAX_READ_LINES,
    MAX_SEARCH_MATCHES,
)


WORKSPACE_ROOT = Path(__file__).resolve().parent
MAX_TEST_OUTPUT_CHARS = 12000


def is_readable_project_file(path):
    return (
        path.is_file()
        and path.name not in EXCLUDED_READ_FILES
        and path.suffix.lower() in ALLOWED_READ_EXTENSIONS
    )


def get_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_files():
    files = [
        path.name
        for path in readable_files()
    ]

    return "\n".join(files) if files else "no readable files"


def find_files(query, max_matches=MAX_PROJECT_SEARCH_MATCHES):
    if not query:
        return "find_files error: query is required"

    if max_matches < 1:
        max_matches = MAX_PROJECT_SEARCH_MATCHES

    max_matches = min(max_matches, MAX_PROJECT_SEARCH_MATCHES)
    query_lower = query.lower()
    matches = []

    for path in readable_files():
        if query_lower in path.name.lower():
            matches.append(path.name)

            if len(matches) >= max_matches:
                break

    if not matches:
        return f"No files found for {query!r}."

    header = (
        f"Found {len(matches)} file match(es) for {query!r}. "
        f"Max matches: {MAX_PROJECT_SEARCH_MATCHES}."
    )

    return header + "\n" + "\n".join(matches)


def readable_files():
    return [
        path
        for path in sorted(WORKSPACE_ROOT.iterdir())
        if is_readable_project_file(path)
    ]


def resolve_readable_file(path):
    target = (WORKSPACE_ROOT / path).resolve()

    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None, f"path is outside workspace: {path}"

    if not target.is_file():
        return None, f"file not found: {path}"

    if not is_readable_project_file(target):
        return None, f"file is not allowed: {path}"

    return target, None


def resolve_writable_file(path, overwrite=False):
    target = (WORKSPACE_ROOT / path).resolve()

    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None, f"path is outside workspace: {path}"

    if target.name in EXCLUDED_READ_FILES:
        return None, f"file is not allowed: {path}"

    if target.suffix.lower() not in ALLOWED_READ_EXTENSIONS:
        return None, f"file extension is not allowed: {path}"

    if target.exists() and not target.is_file():
        return None, f"path is not a file: {path}"

    if target.exists() and not overwrite:
        return None, f"file already exists: {path}. Set overwrite=true to replace it."

    return target, None


def read_file(path, start_line=1, max_lines=MAX_READ_LINES):
    target, error = resolve_readable_file(path)

    if error:
        return f"read_file error: {error}"

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"read_file error: file is not valid UTF-8 text: {path}"
    except OSError as error:
        return f"read_file error: {error}"

    if start_line < 1:
        start_line = 1

    if max_lines < 1:
        max_lines = MAX_READ_LINES

    max_lines = min(max_lines, MAX_READ_LINES)

    total_lines = len(lines)
    start_index = start_line - 1
    end_index = min(start_index + max_lines, total_lines)

    if start_index >= total_lines:
        return f"read_file error: start_line {start_line} is beyond file length {total_lines}"

    numbered_lines = [
        f"{line_number}: {line}"
        for line_number, line in enumerate(lines[start_index:end_index], start=start_line)
    ]
    header = (
        f"Showing {target.name} lines {start_line}-{end_index} of {total_lines}. "
        f"Max lines per read: {MAX_READ_LINES}."
    )

    if end_index < total_lines:
        header += f" More lines are available from line {end_index + 1}."

    return header + "\n" + "\n".join(numbered_lines)


def write_file(path, content, overwrite=False):
    target, error = resolve_writable_file(path, overwrite)

    if error:
        return f"write_file error: {error}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as error:
        return f"write_file error: {error}"

    line_count = len(content.splitlines())
    return f"Wrote {target.name} ({line_count} line(s))."


def replace_in_file(path, old_text, new_text):
    target, error = resolve_readable_file(path)

    if error:
        return f"replace_in_file error: {error}"

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"replace_in_file error: file is not valid UTF-8 text: {path}"
    except OSError as error:
        return f"replace_in_file error: {error}"

    if not old_text:
        return "replace_in_file error: old_text is required"

    count = content.count(old_text)

    if count == 0:
        return "replace_in_file error: old_text not found."

    if count > 1:
        return f"replace_in_file error: old_text matched {count} times. Make it more specific."

    new_content = content.replace(old_text, new_text, 1)

    try:
        target.write_text(new_content, encoding="utf-8")
    except OSError as error:
        return f"replace_in_file error: {error}"

    return f"Replaced 1 occurrence in {target.name}."


def delete_file(path):
    target, error = resolve_readable_file(path)

    if error:
        return f"delete_file error: {error}"

    try:
        target.unlink()
    except OSError as error:
        return f"delete_file error: {error}"

    return f"Deleted {target.name}."


def search_file(path, query, max_matches=MAX_SEARCH_MATCHES):
    target, error = resolve_readable_file(path)

    if error:
        return f"search_file error: {error}"

    if not query:
        return "search_file error: query is required"

    if max_matches < 1:
        max_matches = MAX_SEARCH_MATCHES

    max_matches = min(max_matches, MAX_SEARCH_MATCHES)

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"search_file error: file is not valid UTF-8 text: {path}"
    except OSError as error:
        return f"search_file error: {error}"

    matches = []
    query_lower = query.lower()

    for line_number, line in enumerate(lines, start=1):
        if query_lower in line.lower():
            matches.append(f"{line_number}: {line}")

            if len(matches) >= max_matches:
                break

    if not matches:
        return f"No matches for {query!r} in {target.name}."

    header = (
        f"Found {len(matches)} match(es) for {query!r} in {target.name}. "
        f"Max matches: {MAX_SEARCH_MATCHES}."
    )

    return header + "\n" + "\n".join(matches)


def search_files(query, max_matches=MAX_PROJECT_SEARCH_MATCHES):
    if not query:
        return "search_files error: query is required"

    if max_matches < 1:
        max_matches = MAX_PROJECT_SEARCH_MATCHES

    max_matches = min(max_matches, MAX_PROJECT_SEARCH_MATCHES)
    query_lower = query.lower()
    matches = []

    for path in readable_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line_number, line in enumerate(lines, start=1):
            if query_lower in line.lower():
                matches.append(f"{path.name}:{line_number}: {line}")

                if len(matches) >= max_matches:
                    break

        if len(matches) >= max_matches:
            break

    if not matches:
        return f"No matches for {query!r} in readable project files."

    header = (
        f"Found {len(matches)} project match(es) for {query!r}. "
        f"Max matches: {MAX_PROJECT_SEARCH_MATCHES}."
    )

    return header + "\n" + "\n".join(matches)


def truncate_output(text, max_chars=MAX_TEST_OUTPUT_CHARS):
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n... output truncated ..."


def run_tests(timeout_seconds=30):
    script_path = WORKSPACE_ROOT / "run_tests.py"

    if not script_path.is_file():
        return "run_tests error: run_tests.py not found."

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return f"run_tests error: timed out after {timeout_seconds} second(s)."
    except OSError as error:
        return f"run_tests error: {error}"

    output_parts = []

    if result.stdout:
        output_parts.append(result.stdout.strip())

    if result.stderr:
        output_parts.append(result.stderr.strip())

    output = "\n".join(output_parts).strip()

    if not output:
        output = "(no test output)"

    output = truncate_output(output)

    if result.returncode == 0:
        return "Tests passed.\n" + output

    return f"Tests failed with exit code {result.returncode}.\n" + output


def call_tool(name, arguments):
    if name == "get_time":
        return get_time()

    if name == "list_files":
        return list_files()

    if name == "find_files":
        return find_files(
            arguments["query"],
            arguments.get("max_matches", MAX_PROJECT_SEARCH_MATCHES),
        )

    if name == "read_file":
        return read_file(
            arguments["path"],
            arguments.get("start_line", 1),
            arguments.get("max_lines", MAX_READ_LINES),
        )

    if name == "write_file":
        return write_file(
            arguments["path"],
            arguments["content"],
            arguments.get("overwrite", False),
        )

    if name == "replace_in_file":
        return replace_in_file(
            arguments["path"],
            arguments["old_text"],
            arguments["new_text"],
        )

    if name == "delete_file":
        return delete_file(
            arguments["path"],
        )

    if name == "search_file":
        return search_file(
            arguments["path"],
            arguments["query"],
            arguments.get("max_matches", MAX_SEARCH_MATCHES),
        )

    if name == "run_tests":
        return run_tests(
            arguments.get("timeout_seconds", 30),
        )

    if name == "search_files":
        return search_files(
            arguments["query"],
            arguments.get("max_matches", MAX_PROJECT_SEARCH_MATCHES),
        )

    return f"unknown tool: {name}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current local time.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List readable text files in the current project directory.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Find readable project files by matching text in the file name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The file name text to search for, such as memory or test.",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": f"The maximum number of file names to return. Defaults to {MAX_PROJECT_SEARCH_MATCHES} and cannot exceed {MAX_PROJECT_SEARCH_MATCHES}.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the current project directory. Prefer search_file or search_files first when the user asks about a specific function, setting, or concept and the line number is unknown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative file path to read, such as AI_agent.py or README.md.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "The 1-based line number to start reading from. Defaults to 1.",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": f"The maximum number of lines to return. Defaults to {MAX_READ_LINES} and cannot exceed {MAX_READ_LINES}.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text content to a project file. This changes files and requires user confirmation before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative file path to write, such as notes.txt or docs/plan.md.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete text content to write to the file.",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Whether to replace an existing file. Defaults to false.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "Replace one exact text snippet in a readable project file. This changes files and requires user confirmation before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative file path to edit, such as config.py or README.md.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The exact existing text to replace. It must match exactly once.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The replacement text.",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete one readable project file. This is destructive and requires user confirmation before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative file path to delete, such as notes.txt.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": "Search for a keyword or phrase in one text file from the current project directory. Use this before reading a large file when looking for a specific function, setting, or concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative file path to search, such as AI_agent.py or tools.py.",
                    },
                    "query": {
                        "type": "string",
                        "description": "The keyword or phrase to search for.",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": f"The maximum number of matches to return. Defaults to {MAX_SEARCH_MATCHES} and cannot exceed {MAX_SEARCH_MATCHES}.",
                    },
                },
                "required": ["path", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the project's unittest suite through run_tests.py.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum number of seconds to wait for tests. Defaults to 30.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a keyword or phrase across all readable text files in the current project directory. Use this when the user asks where something is defined or used but does not specify a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The keyword or phrase to search for.",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": f"The maximum number of project-wide matches to return. Defaults to {MAX_PROJECT_SEARCH_MATCHES} and cannot exceed {MAX_PROJECT_SEARCH_MATCHES}.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
