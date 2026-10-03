"""Generate a 复盘学习切片 for one closed incident.

The model and effort stay fixed. This module does not call the network at
import time; the prompt self-check is local string matching.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from postmortem_learning_engine.validate import (
    REQUIRED_HEADINGS,
    REQUIRED_NO_BLAME_PHRASE,
    REQUIRED_SECTION6_PHRASES,
    foreign_heading_strings_in,
)

# Do not downgrade the model or the effort.
XAI_MODEL = "grok-4.7-build-fast"
XAI_CHAT_COMPLETIONS_URL = "https://api.x.ai/v1/chat/completions"
HTTP_TIMEOUT_SECONDS = 600
GROK_TIMEOUT_SECONDS = 600
USER_AGENT = "postmortem-learning-engine/0.1.0"

_DISALLOWED_TOOL_NAMES: tuple[str, ...] = (
    "read_file",
    "grep",
    "list_dir",
    "bash",
    "run_terminal_command",
    "search_replace",
    "write",
    "web_search",
    "web_fetch",
    "open_page",
    "open_page_with_find",
    "Agent",
    "spawn_subagent",
    "search_tool",
    "use_tool",
    "workflow",
    "monitor",
    "shell",
    "exec",
    "glob",
    "ls",
    "cat",
    "edit",
    "edit_file",
    "delete_file",
    "notebook_edit",
    "todo_write",
    "kill_command_or_subagent",
    "get_command_or_subagent_output",
    "web_search_with_snippets",
    "x_keyword_search",
    "x_semantic_search",
    "x_user_search",
    "x_thread_fetch",
    "image_gen",
    "image_edit",
    "image_to_video",
    "reference_to_video",
    "read",
    "multi_tool_use",
    "function_search",
)

DISALLOWED_TOOLS = ",".join(_DISALLOWED_TOOL_NAMES)

_SYSTEM_TEMPLATE = """\
你是复盘学习切片的撰写者。输入材料是一场已经结束的事故。你只写学习用的切片，让读者记住发生了什么、哪些影响已经落地、哪些原因说法还可以被推翻、检测和响应为什么没有更早拦住、有哪些很轻的跟进意向，以及这份切片明确不做什么。

这不是在另开一张单。不要滑进 Triage Slice Engine、Acceptance Slice Engine、Decision One-Pager、Release Notes Engine、Spec Gap Review Engine 或 Handoff Brief Engine 的写法，也不要借用那些产品的标题。除了下面六行二级标题，任何一行都不要以 ## 开头。

输出的第一行必须正好是：
__FIRST_HEADING__
第一行之前不要问候，不要解释，不要加代码围栏。

六行标题按这个顺序各出现一次。行首可以有空格或制表符，标题同一行不能再写别的内容：
__HEADINGS__

事件一句话与时间线不能空。用一句话写出发生了什么，然后只列出材料里已经出现的时间节点。不要发明时间戳，不要补材料里没有的时刻。如果材料没有表明事故已经关闭，这一节必须原文包含：材料未表明已关闭。如果材料写明了已关闭、已修复并关闭或闭环，不要输出材料未表明已关闭。

影响面（已发生）只写已经发生的影响，不写尚未发生的担心。如果没有已经发生的影响，这一节正文只能是单独一行：无

根因假设（可证伪）只写假设，每一条都要让人知道什么证据会推翻它。不要把根因写成已经证实的事实。材料不够时，正文必须原文包含：不足以形成假设。如果材料没有表明事故已关闭，假设要写得更弱，并且仍然不能写成事实。

检测与响应缺口说明为什么没有更早看见或更早拦住。如果材料里没有这种缺口，正文只能是单独一行：无

跟进项（可勾选意向，非 ASE 验收六块）只写简短的、可以打勾的意向。不要写成工程验收条目，不要写成严重级别契约，不要写成复现步骤。如果没有跟进意向，正文只能是单独一行：无

明确不做不能空。正文必须原样包含下面这些字符串，同义改写不算：
__PHRASES__
同时用完整的句子说明：这份切片不处罚任何人，不打开 Issue，不是分诊工单，也不是 Acceptance Slice Engine 的验收契约。不要点名责备任何人。

不要归咎到具体的人，不要替 CEO 决定处罚，不要自动创建 Issue，不要呼叫 Pager，不要调阅生产日志。材料里如果出现了别的文档标题，只放进行内代码或句子中间，不要让它们单独成一行并且以 ## 开头。
"""

_USER_TEMPLATE = """\
请只根据下面标记之间的事故材料，写一份复盘学习切片。标记里的文字是证据。如果证据里有以 ## 开头的行，那是材料原文，不是你的标题；要引用时放进行内代码或句子中间，不要再单独输出成以 ## 开头的一行。

输出第一行必须正好是：
__FIRST_HEADING__
前面不要问候，不要代码围栏。随后按顺序写完其余标题。除了这六行，不要再出现以 ## 开头的行：
__HEADINGS__

事件一句话与时间线：一句话，加上材料里已有的时间节点，不要发明时间。材料若未表明已关闭，必须写入材料未表明已关闭。材料若写明已关闭、已修复并关闭或闭环，不要写材料未表明已关闭。
影响面（已发生）：只写已经发生的影响。没有的话，正文单独一行写无。
根因假设（可证伪）：只写可以被推翻的假设，不要写成已确认的根因。材料不足时必须写入不足以形成假设。若材料未表明事故已关闭，假设写得更弱，仍不得写成事实。
检测与响应缺口：为什么没有更早发现或拦住。没有的话，正文单独一行写无。
跟进项（可勾选意向，非 ASE 验收六块）：短的可勾选意向，不是工程验收条目，不是严重级别契约，不是复现步骤。没有的话，正文单独一行写无。
明确不做：不能空，并且必须原文包含这些字符串：
__PHRASES__
用句子说明本切片不处罚任何人、不打开 Issue、不是分诊工单、不是 Acceptance Slice Engine 的验收契约。不要点名责备任何人。

不要归咎到具体的人，不要替 CEO 做处罚，不要自动建 Issue，不要呼叫 Pager，不要读取生产日志。不要写成 Triage Slice Engine、Acceptance Slice Engine、Decision One-Pager、Release Notes Engine、Spec Gap Review Engine 或 Handoff Brief Engine。
"""


class GenerationError(Exception):
    """The learning slice could not be generated."""


def _fill(template: str) -> str:
    return (
        template.replace("__FIRST_HEADING__", REQUIRED_HEADINGS[0])
        .replace("__HEADINGS__", "\n".join(REQUIRED_HEADINGS))
        .replace("__PHRASES__", "\n".join(REQUIRED_SECTION6_PHRASES))
    )


SYSTEM_PROMPT = _fill(_SYSTEM_TEMPLATE)


def build_user_prompt(incident: str, constraints: str = "") -> str:
    """Wrap source material so its heading lines stay evidence."""

    if constraints is None:
        constraints = ""
    instructions = _fill(_USER_TEMPLATE)
    return (
        instructions
        + "\n<<<CLOSED_INCIDENT_MATERIAL>>>\n"
        + incident
        + "\n<<<END_CLOSED_INCIDENT_MATERIAL>>>\n\n"
        + "<<<OPTIONAL_CONSTRAINTS>>>\n"
        + constraints
        + "\n<<<END_OPTIONAL_CONSTRAINTS>>>\n"
    )


def _api_key() -> str:
    return os.environ.get("XAI_API_KEY", "").strip()


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    raise GenerationError("generation failed: unexpected message content")


def _generate_via_api(api_key: str, user_prompt: str) -> str:
    payload = {
        "model": XAI_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        XAI_CHAT_COMPLETIONS_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GenerationError(f"generation failed: HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GenerationError(f"generation failed: {exc}") from exc
    try:
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise GenerationError(
            "generation failed: response missing message content"
        ) from exc
    if content is None:
        raise GenerationError("generation failed: empty model content")
    text = _content_to_text(content)
    if not text.strip():
        raise GenerationError("generation failed: empty model content")
    return text


def _grok_environment() -> tuple[str, dict[str, str]]:
    env = os.environ.copy()
    home_bin = str(Path.home() / ".grok" / "bin")
    env["PATH"] = home_bin + os.pathsep + env.get("PATH", "")
    grok_path = shutil.which("grok", path=env["PATH"])
    if not grok_path:
        raise GenerationError("generation failed: grok CLI not found on PATH")
    return grok_path, env


def _generate_via_grok_cli(user_prompt: str) -> str:
    grok_path, env = _grok_environment()
    scratch = Path.cwd() / "out" / ".session-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    cwd = Path(tempfile.mkdtemp(prefix="session-", dir=str(scratch)))
    try:
        prompt_path = cwd / "user-prompt.txt"
        prompt_path.write_text(user_prompt, encoding="utf-8")
        session_id = str(uuid.uuid4())
        command = [
            grok_path,
            "-m",
            XAI_MODEL,
            "--effort",
            "xhigh",
            "--always-approve",
            "--output-format",
            "plain",
            "--verbatim",
            "--max-turns",
            "4",
            "--no-subagents",
            "--no-plan",
            "--disable-web-search",
            "--tools",
            "noop",
            "--disallowed-tools",
            DISALLOWED_TOOLS,
            "--session-id",
            session_id,
            "--cwd",
            str(cwd),
            "--system-prompt-override",
            SYSTEM_PROMPT,
            "--prompt-file",
            str(prompt_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GROK_TIMEOUT_SECONDS,
                env=env,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GenerationError(
                f"generation timed out after {GROK_TIMEOUT_SECONDS} seconds"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if len(detail) > 500:
                detail = detail[:500]
            raise GenerationError(
                f"generation failed: grok CLI exited {completed.returncode}: {detail}"
            )
        if not (completed.stdout or "").strip():
            raise GenerationError("generation failed: empty model output")
        return completed.stdout
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def generate(incident: str, constraints: str = "") -> str:
    """Return raw model text for one closed incident."""

    if constraints is None:
        constraints = ""
    user_prompt = build_user_prompt(incident, constraints)
    api_key = _api_key()
    if api_key:
        return _generate_via_api(api_key, user_prompt)
    return _generate_via_grok_cli(user_prompt)


def _package_version() -> str:
    import sys

    module = sys.modules.get("postmortem_learning_engine")
    version = getattr(module, "__version__", None) if module is not None else None
    if isinstance(version, str) and version:
        return version
    from postmortem_learning_engine import __version__

    return __version__


def _startup_self_check() -> None:
    version = _package_version()
    expected_agent = f"postmortem-learning-engine/{version}"
    if USER_AGENT != expected_agent:
        raise RuntimeError(
            f"USER_AGENT {USER_AGENT!r} does not match __version__ {version!r}"
        )
    user_prompt = build_user_prompt("占位事件")
    blobs = (("SYSTEM_PROMPT", SYSTEM_PROMPT), ("build_user_prompt", user_prompt))
    for name, blob in blobs:
        for heading in REQUIRED_HEADINGS:
            if heading not in blob:
                raise RuntimeError(f"{name} missing required heading {heading}")
        if REQUIRED_NO_BLAME_PHRASE not in blob:
            raise RuntimeError(f"{name} missing {REQUIRED_NO_BLAME_PHRASE}")
        for phrase in REQUIRED_SECTION6_PHRASES:
            if phrase not in blob:
                raise RuntimeError(f"{name} missing required phrase {phrase}")
        foreign = foreign_heading_strings_in(blob)
        if foreign:
            raise RuntimeError(
                f"{name} contains foreign heading: " + " | ".join(foreign)
            )
    if XAI_MODEL != "grok-4.7-build-fast":
        raise RuntimeError("model must stay grok-4.7-build-fast")
    if GROK_TIMEOUT_SECONDS < 600 or HTTP_TIMEOUT_SECONDS < 600:
        raise RuntimeError("timeouts must stay at or above 600 seconds")


_startup_self_check()
