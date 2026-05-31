# AI Tool Calling Agent

这是一个用于学习 AI Agent 和 tool calling 的小项目。

它演示了一个基本 Agent 如何：

- 接收用户输入
- 让模型判断是否需要调用工具
- 由 Python 执行真实工具函数
- 把工具结果回传给模型
- 让模型生成最终回答
- 保存短期上下文和完整日志

## 项目结构

```text
AI_agent.py        Agent 主流程：对话循环、请求模型、处理 tool_calls
tools.py           工具层：工具函数、TOOLS 工具说明书、call_tool 路由
memory.py          记忆层：读取/保存 history、追加 log、裁剪 messages
config.py          配置层：读取模型名、base_url、历史文件名等配置
.env               本地环境变量：API key、模型名、配置覆盖项
.gitignore         Git 忽略规则，避免提交密钥和本地运行数据
chat_history.json  最近上下文快照，供模型重启后恢复记忆
chat_log.jsonl     完整对话流水日志，供人查看和排查
```

## 运行方式

先在 `.env` 中配置 API key：

```env
DEEPSEEK_API_KEY=your_api_key_here
MODEL=deepseek-v4-flash
BASE_URL=https://api.deepseek.com
MAX_HISTORY_MESSAGES=20
MAX_FILE_READ_LINES_PER_TURN=120
HISTORY_FILE=chat_history.json
LOG_FILE=chat_log.jsonl
ALLOWED_READ_EXTENSIONS=.py,.md,.txt,.json,.jsonl
EXCLUDED_READ_FILES=.env,chat_history.json,chat_log.jsonl,todos.json
MAX_READ_LINES=120
MAX_SEARCH_MATCHES=20
MAX_PROJECT_SEARCH_MATCHES=30
SYSTEM_PROMPT=You are a tiny AI agent. Use tools when they are useful.
```

然后运行：

```bash
python AI_agent.py
```

退出：

```text
q
```

## 当前工具

当前 `tools.py` 中有五个工具：

```text
get_time()
```

用于获取当前本地时间。

```text
list_files()
```

用于列出当前项目目录下可读取的文本文件。

```text
read_file(path, start_line=1, max_lines=120)
```

用于读取当前项目目录下的文本文件。返回内容会带行号，并默认最多读取 120 行。
为了安全，它只允许读取常见文本文件类型，不允许读取 `.env`。

```text
search_file(path, query, max_matches=20)
```

用于在单个文本文件中搜索关键词，返回匹配行号和内容。适合先定位相关位置，再用 `read_file` 读取附近片段。

```text
search_files(query, max_matches=30)
```

用于在当前项目所有可读文本文件中搜索关键词，返回 `文件名:行号:内容`。适合不知道内容在哪个文件时先做全项目定位。

## Tool Calling 流程

一次工具调用的大致流程：

```text
用户输入
  ↓
AI_agent.py 把 messages 和 TOOLS 发给模型
  ↓
模型判断是否需要工具
  ↓
如果需要，模型返回 assistant_message.tool_calls
  ↓
AI_agent.py 调用 tools.call_tool()
  ↓
tools.py 执行真实 Python 函数
  ↓
AI_agent.py 把 tool result 放回 messages
  ↓
再次请求模型
  ↓
模型根据工具结果生成最终回答
```

## 记忆机制

项目里有两类记忆文件：

```text
chat_history.json
```

给模型看的最近上下文快照。它会被 `MAX_HISTORY_MESSAGES` 裁剪，避免上下文无限增长。

```text
chat_log.jsonl
```

给人看的完整流水日志。它会追加保存，不裁剪，适合排查和回放。

一句话区别：

```text
history 是工作记忆，log 是档案记录。
```

## 配置机制

`config.py` 会读取 `.env` 中的环境变量。

如果 `.env` 没有配置，就使用代码里的默认值。

这样可以做到：

- 不把 API key 写死在代码里
- 换模型不用改主流程
- 调整历史长度不用改 memory 逻辑

## Git 忽略

`.gitignore` 会忽略：

```text
.env
__pycache__/
*.py[cod]
chat_history.json
chat_log.jsonl
todos.json
.venv/
venv/
```

这些文件通常包含密钥、本地缓存、运行数据或虚拟环境，不适合提交到 Git。
