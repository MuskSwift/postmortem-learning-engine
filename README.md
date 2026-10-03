# postmortem-learning-engine

已关闭事故的复盘学习切片。命令行读取一份已经结束的事故材料，写出六段学习记录：一句话和材料里已有的时间线、已经发生的影响、可以推翻的根因假设、检测与响应为什么没能更早拦住、可以打勾的跟进意向，以及这份切片明确不做的事。

它是学习切片。它不是分诊单，不是验收契约，不是决策一页纸，不是发布说明，不是规格缺口审查，也不是交接简报。它不包装 Triage Slice Engine、Acceptance Slice Engine、Decision One-Pager、Release Notes Engine、Spec Gap Review Engine 或 Handoff Brief Engine。

裸的二级标题 `## 影响面` 会被拒绝。本工具自己的标题是 `## 影响面（已发生）`。`## 影响面（已发生）` 不能被当成裸标题 `## 影响面`。

六个二级标题，按这个顺序各出现一次：

1. `## 事件一句话与时间线`
2. `## 影响面（已发生）`
3. `## 根因假设（可证伪）`
4. `## 检测与响应缺口`
5. `## 跟进项（可勾选意向，非 ASE 验收六块）`
6. `## 明确不做`

最后一节必须原文包含 `不归咎个人`，以及 `不替 CEO 处罚`、`不自动建 Issue`、`不是 Triage`、`不是 ASE`。同义改写不算。

## 安装

需要 Python 3.9 或更高版本。运行时只用标准库。在仓库根目录：

```bash
pip install -e .
```

安装后的控制台命令是 `postmortem-learning-engine`。不安装时：

```bash
PYTHONPATH=. python3 -m postmortem_learning_engine --help
```

`PYTHONPATH=. python3 -m postmortem_learning_engine` 与上面是同一条入口。

## 鉴权

凭证自己准备。设置 `XAI_API_KEY`，或使用本机已经登录的 `grok` 命令行。不要把密钥写进仓库，不要提交密钥。

两条路径的模型都是 `grok-4.7-build-fast`。

- 环境变量 `XAI_API_KEY` 去掉空白后非空：向 `https://api.x.ai/v1/chat/completions` 发请求。
- 否则走 Option B：调用已经登录的 `grok` 命令行。程序会把 `~/.grok/bin` 加到 `PATH` 前面。这条路径固定带 `--effort xhigh`。

模型保持 `grok-4.7-build-fast`。Option B 的 effort 保持 `xhigh`。

HTTP 超时大于等于 600 秒。Option B 子进程超时大于等于 600 秒。超时是非零退出。输出若缺少六个标题里的任何一个，也不是成功：`--out` 会删掉，退出码为 `1`。

## 示例

`examples/sample-incident.md` 里的事故状态已经是关闭。下面的命令读这份材料，加上 `examples/sample-constraints.md`，把切片写到 `out/sample-postmortem-learning.md`。

```bash
python3 -m postmortem_learning_engine \
  --incident-file examples/sample-incident.md \
  --constraints-file examples/sample-constraints.md \
  --out out/sample-postmortem-learning.md
```

未指定 `--out` 时，默认路径是 `./out/<slug>-postmortem-learning.md`。

## 样例输入输出

- 事故材料：`examples/sample-incident.md`。这场事故已经关闭。
- 可选约束：`examples/sample-constraints.md`。
- 手写的合法切片：`examples/sample-output.md`。

## 输出契约

校验会拒绝下列标题。外来标题都写在行内代码里，不是本文的二级标题。

- 裸标题行 `## 影响面`。要求的标题是 `## 影响面（已发生）`，这行不得被当成裸标题 `## 影响面`。
- Triage 标题组：`## 一句话问题`、`## 建议 sev`、`## 复现步骤`、`## 影响面`、`## 临时绕过`、`## 建议下一步与明确不做`。
- ASE 标题组：`## 工单目标`、`## 验收条目`、`## 非本单 / 明确不做`、`## 风险与 sev 提示`、`## 给实现的边界`、`## 待确认的开放问题`。
- DOP 标题组：`## 问题陈述`、`## 选项对比`、`## 推荐`、`## 否决或缓做`、`## 待核实事实`。
- RN 标题组：`## 用户可见变化`、`## 为什么重要`、`## 破坏性 / 迁移`、`## 已知限制`、`## 明确不写`。
- SpecGap 标题组：`## 声称要交付什么`、`## 含糊与不可测表述`、`## 缺失的验收或边界`、`## 与已知禁项的冲突`、`## 建议补问清单`。
- Handoff 标题组：`## 交接对象与一句话状态`、`## 已完成（可核对）`、`## 未决与阻塞`、`## 请接收方立刻做什么`、`## 风险与过期信息`。
- 任何其他意外的 `##` 行。材料原文里的第三方 `##` 行不得变成额外的模式标题。

`## 明确不做` 必须非空，并且必须包含这些精确子串，同义改写不算：`不归咎个人`、`不替 CEO 处罚`、`不自动建 Issue`、`不是 Triage`、`不是 ASE`。

## 退出码

- `0`：成功。标准输出打印输出路径。旁边若有旧的失败摘录，会删掉。
- `1`：生成失败，或校验失败。校验失败时仍会删除 `--out`，并在该路径旁边写一份被 git 忽略的短摘录 `<stem>.fail.txt`。例如 `out/sample-postmortem-learning.md` 旁边是 `out/sample-postmortem-learning.fail.txt`。`--out` 不在 `out/` 里时，`*.fail.txt` 同样被忽略。标准错误仍会逐条打印错误。这份摘录不是成功的学习切片。用法错误，以及从未写出 `--out` 的生成失败，不会写这份摘录。
- `2`：用法错误（缺少事故材料、文件不存在、不是合法 UTF-8）。
- `130`：中断。

## 稳定标题检查

下面的脚本会真实调用模型，可能要好几分钟。它把示例事故跑两遍，并检查六个标题都在：

```bash
bash scripts/assert_stable_headings.sh
```

通过时打印 `PASS`。
