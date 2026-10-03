"""Validate a closed-incident postmortem learning slice.

Only markdown H2 lines are schema. Phrases that merely appear in a section
body are not treated as headings.
"""

from __future__ import annotations

REQUIRED_HEADINGS: tuple[str, ...] = (
    "## 事件一句话与时间线",
    "## 影响面（已发生）",
    "## 根因假设（可证伪）",
    "## 检测与响应缺口",
    "## 跟进项（可勾选意向，非 ASE 验收六块）",
    "## 明确不做",
)

REQUIRED_NO_BLAME_PHRASE = "不归咎个人"

REQUIRED_SECTION6_PHRASES: tuple[str, ...] = (
    REQUIRED_NO_BLAME_PHRASE,
    "不替 CEO 处罚",
    "不自动建 Issue",
    "不是 Triage",
    "不是 ASE",
)

# Foreign H2 strings. "## 明确不做" is our sixth heading and is intentionally
# absent. The bare triage heading "## 影响面" is matched with an explicit
# exception so "## 影响面（已发生）" is not treated as that heading.
_TRIAGE_HEADINGS: tuple[str, ...] = (
    "## 一句话问题",
    "## 建议 sev",
    "## 复现步骤",
    "## 影响面",
    "## 临时绕过",
    "## 建议下一步与明确不做",
)

_ASE_HEADINGS: tuple[str, ...] = (
    "## 工单目标",
    "## 验收条目",
    "## 非本单 / 明确不做",
    "## 风险与 sev 提示",
    "## 给实现的边界",
    "## 待确认的开放问题",
)

_DOP_HEADINGS: tuple[str, ...] = (
    "## 问题陈述",
    "## 选项对比",
    "## 推荐",
    "## 否决或缓做",
    "## 待核实事实",
)

_RELEASE_NOTES_HEADINGS: tuple[str, ...] = (
    "## 用户可见变化",
    "## 为什么重要",
    "## 破坏性 / 迁移",
    "## 已知限制",
    "## 明确不写",
)

_SPEC_GAP_HEADINGS: tuple[str, ...] = (
    "## 声称要交付什么",
    "## 含糊与不可测表述",
    "## 缺失的验收或边界",
    "## 与已知禁项的冲突",
    "## 建议补问清单",
)

_HANDOFF_HEADINGS: tuple[str, ...] = (
    "## 交接对象与一句话状态",
    "## 已完成（可核对）",
    "## 未决与阻塞",
    "## 请接收方立刻做什么",
    "## 风险与过期信息",
)

FOREIGN_HEADINGS: tuple[str, ...] = (
    _TRIAGE_HEADINGS
    + _ASE_HEADINGS
    + _DOP_HEADINGS
    + _RELEASE_NOTES_HEADINGS
    + _SPEC_GAP_HEADINGS
    + _HANDOFF_HEADINGS
)

_OWN_IMPACT_HEADING = "## 影响面（已发生）"
_BARE_IMPACT_HEADING = "## 影响面"


def line_matches_foreign_heading(stripped: str, heading: str) -> bool:
    """Return whether a stripped line starts with one denylisted H2.

    A normal denylisted heading matches when the line equals it, or continues
    with a space or a tab. The bare triage heading "## 影响面" is wider: any
    continuation matches except a line that starts with our own
    "## 影响面（已发生）".
    """

    if heading == _BARE_IMPACT_HEADING:
        if stripped.startswith(_OWN_IMPACT_HEADING):
            return False
        return stripped.startswith(_BARE_IMPACT_HEADING)
    if stripped == heading:
        return True
    if stripped.startswith(heading + " ") or stripped.startswith(heading + "\t"):
        return True
    return False


def matching_foreign_heading(stripped: str) -> str | None:
    for heading in FOREIGN_HEADINGS:
        if line_matches_foreign_heading(stripped, heading):
            return heading
    return None


def foreign_heading_strings_in(text: str) -> list[str]:
    """Return denylisted H2 strings that occur in text.

    Our heading "## 影响面（已发生）" contains the characters of the bare
    triage heading as a prefix. Those occurrences are not foreign.
    """

    found: list[str] = []
    for heading in FOREIGN_HEADINGS:
        if heading == _BARE_IMPACT_HEADING:
            if _bare_impact_heading_occurs(text):
                found.append(heading)
        elif heading in text:
            found.append(heading)
    return found


def _bare_impact_heading_occurs(text: str) -> bool:
    start = 0
    while True:
        index = text.find(_BARE_IMPACT_HEADING, start)
        if index < 0:
            return False
        if text.startswith(_OWN_IMPACT_HEADING, index):
            start = index + len(_OWN_IMPACT_HEADING)
            continue
        return True


def _h2_lines(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        stripped = line.lstrip(" \t")
        if stripped.startswith("## "):
            found.append((index, stripped))
    return found


def _section_body(lines: list[str], heading_index: int, h2_indexes: list[int]) -> str:
    end = len(lines)
    for index in h2_indexes:
        if index > heading_index:
            end = index
            break
    return "\n".join(lines[heading_index + 1 : end]).strip()


def validate_or_errors(text: str) -> list[str]:
    """Return human-readable errors. An empty list means the slice is valid."""

    errors: list[str] = []
    if not isinstance(text, str):
        return ["document must be text"]

    if not text.lstrip().startswith(REQUIRED_HEADINGS[0]):
        errors.append(f"document must start with {REQUIRED_HEADINGS[0]}")

    h2_lines = _h2_lines(text)
    h2_indexes = [index for index, _stripped in h2_lines]
    required_set = set(REQUIRED_HEADINGS)
    source_lines = text.splitlines()

    positions: dict[str, list[int]] = {heading: [] for heading in REQUIRED_HEADINGS}
    for index, stripped in h2_lines:
        if stripped in positions:
            positions[stripped].append(index)

    found_in_required_order: list[tuple[int, str]] = []
    for heading in REQUIRED_HEADINGS:
        found = positions[heading]
        if not found:
            errors.append(f"missing required heading: {heading}")
        elif len(found) > 1:
            errors.append(f"duplicate heading: {heading}")
        else:
            found_in_required_order.append((found[0], heading))

    previous_index = -1
    previous_heading: str | None = None
    for index, heading in found_in_required_order:
        if previous_heading is not None and index <= previous_index:
            errors.append(
                f"heading out of order: {heading} appears before {previous_heading}"
            )
        previous_index = index
        previous_heading = heading

    follow_heading = REQUIRED_HEADINGS[4]
    clear_heading = REQUIRED_HEADINGS[5]
    follow_at = positions[follow_heading]
    clear_at = positions[clear_heading]
    if clear_at and (not follow_at or min(clear_at) < min(follow_at)):
        errors.append(
            f"heading {clear_heading} appears before {follow_heading}"
        )

    for _index, stripped in h2_lines:
        if stripped in required_set:
            continue
        foreign = matching_foreign_heading(stripped)
        if foreign is not None:
            if stripped == foreign:
                errors.append(f"foreign heading is not allowed: {foreign}")
            else:
                errors.append(
                    f"foreign heading is not allowed: {foreign} (line: {stripped})"
                )
        else:
            errors.append(f"unexpected heading: {stripped}")

    for heading in REQUIRED_HEADINGS:
        found = positions[heading]
        if not found:
            continue
        body = _section_body(source_lines, found[0], h2_indexes)
        if not body:
            errors.append(f"empty section body: {heading}")
        if heading == clear_heading:
            for phrase in REQUIRED_SECTION6_PHRASES:
                if phrase not in body:
                    errors.append(
                        f"heading {clear_heading} is missing required phrase: {phrase}"
                    )

    return errors


def _self_check_matcher() -> None:
    if _OWN_IMPACT_HEADING not in REQUIRED_HEADINGS:
        raise RuntimeError("own impact heading missing from REQUIRED_HEADINGS")
    if _BARE_IMPACT_HEADING not in FOREIGN_HEADINGS:
        raise RuntimeError("bare triage heading missing from the denylist")
    if any(heading in FOREIGN_HEADINGS for heading in REQUIRED_HEADINGS):
        raise RuntimeError("a required heading was placed on the foreign denylist")
    if line_matches_foreign_heading(_OWN_IMPACT_HEADING, _BARE_IMPACT_HEADING):
        raise RuntimeError("## 影响面（已发生） must not match bare ## 影响面")
    if line_matches_foreign_heading(
        _OWN_IMPACT_HEADING + " 尾注", _BARE_IMPACT_HEADING
    ):
        raise RuntimeError("a longer own impact line must not match bare ## 影响面")
    if not line_matches_foreign_heading(_BARE_IMPACT_HEADING, _BARE_IMPACT_HEADING):
        raise RuntimeError("bare ## 影响面 must match")
    if not line_matches_foreign_heading("## 影响面更多", _BARE_IMPACT_HEADING):
        raise RuntimeError("bare ## 影响面 prefix must match when it is not our heading")
    if not line_matches_foreign_heading("## 工单目标 extra", "## 工单目标"):
        raise RuntimeError("foreign heading plus space must match")
    if line_matches_foreign_heading("## 工单目标extra", "## 工单目标"):
        raise RuntimeError("foreign heading plus immediate text must not match")
    if foreign_heading_strings_in(_OWN_IMPACT_HEADING):
        raise RuntimeError("own impact heading string was treated as foreign")
    if _BARE_IMPACT_HEADING not in foreign_heading_strings_in("see\n## 影响面\n"):
        raise RuntimeError("bare impact heading string was not detected")


_self_check_matcher()
