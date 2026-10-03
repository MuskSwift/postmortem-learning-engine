#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo FAIL; exit 1; }

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export PATH="${HOME}/.grok/bin:${PATH}"

OUT1=""
OUT2=""
cleanup() {
  if [[ -n "${OUT1}" ]]; then
    rm -f "${OUT1}"
  fi
  if [[ -n "${OUT2}" ]]; then
    rm -f "${OUT2}"
  fi
}
trap cleanup EXIT

INCIDENT="examples/sample-incident.md"
CONSTRAINTS="examples/sample-constraints.md"

if [[ ! -f "${INCIDENT}" ]]; then
  echo FAIL
  exit 1
fi

OUT1="$(mktemp)" || { echo FAIL; exit 1; }
OUT2="$(mktemp)" || { echo FAIL; exit 1; }

cmd=(python3 -m postmortem_learning_engine --incident-file "${INCIDENT}")
if [[ -f "${CONSTRAINTS}" ]]; then
  cmd+=(--constraints-file "${CONSTRAINTS}")
fi

if ! "${cmd[@]}" --out "${OUT1}"; then
  echo FAIL
  exit 1
fi
if ! "${cmd[@]}" --out "${OUT2}"; then
  echo FAIL
  exit 1
fi

headings=(
  "## 事件一句话与时间线"
  "## 影响面（已发生）"
  "## 根因假设（可证伪）"
  "## 检测与响应缺口"
  "## 跟进项（可勾选意向，非 ASE 验收六块）"
  "## 明确不做"
)

for heading in "${headings[@]}"; do
  if ! grep -qF -- "${heading}" "${OUT1}"; then
    echo FAIL
    exit 1
  fi
  if ! grep -qF -- "${heading}" "${OUT2}"; then
    echo FAIL
    exit 1
  fi
done

echo PASS
exit 0
