<div align="center">

# Α Aletheia

**让 Agent 技能路由不再黑箱。**
*把任务交给对的 Skill —— 并把整个过程摊开给你看。*

[![License: MIT](https://img.shields.io/badge/license-MIT-534AB7?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-1D9E75?style=flat-square)](https://www.python.org/)
[![Agent Skills](https://img.shields.io/badge/spec-Agent%20Skills-BA7517?style=flat-square)](https://agentskills.io/specification)
[![Version](https://img.shields.io/badge/version-1.8.0-888780?style=flat-square)](CHANGELOG.md)

[English](README.md) · **简体中文**

</div>

---

Aletheia（Ἀλήθεια，希腊语）是**「解蔽」** principles——真理即**未被遮蔽**之物。它正是「黑箱」的反义词，而这也正是本项目要解决的问题：Agent 悄悄选了个 Skill、悄悄跑完、给你一个你无法审计的结果。

Aletheia 把任务路由到正确的已安装 Skill，**并让路由过程可见**：考虑了什么、否决了什么以及为什么、实际执行了什么、验证了什么、还有哪些没验证。任何不可逆或对外的操作之前，它会停下来问你。

## 为什么需要它

Agent 工作里反复出现三类问题：

| 问题 | 表现 | Aletheia 的对策 |
| --- | --- | --- |
| **静默选择** | 明明有专业 Skill，Agent 却凭通用常识即兴发挥 | 强制预检 + 候选披露 |
| **选错** | 只按关键词匹配，抓了一个错的 Skill | 展示被否决的候选及原因 |
| **执行不可审计** | 只说一句「搞定了」，不交代跑了什么、验证了什么 | 五阶段轨迹：意图 → 候选 → 决断 → 操作 → 结论 |

外加两个让长会话很痛苦的问题：**上下文漂移** 和 **技能库噪音**。

## 你会得到什么

- **整个技能库的管家** —— 个人目录和插件缓存里的每一个 skill 都清点得到
- **由你决定谁做选择** —— 默认自主，或你接管按序号选；装时选一次，之后一句话切换
- **可见路由** —— 五阶段披露，包含被**否决**的候选
- **可数的进度** —— 只报「已完成步骤 / 声明总步数」，四种状态，绝不编造 ETA
- **停顿确认门** —— 破坏性、对外发送、财务、范围有歧义的操作前先确认；但绝不拦截无害的本地读取
- **会话级作用域** —— 本次任务只启用需要的 Skill，不带整个库
- **上下文压力监测** —— 实测 transcript 字节数、分级提醒，并给出对应宿主的 `/compact` 或 `/new` 命令
- **只读 CLI** —— 纯标准库清点、发现、路由、作用域、进度与离线评测

## 安装

```bash
git clone https://github.com/Xiranwuxianxi/aletheia.git
cd aletheia

# 安装到目标项目，并显式启用常驻路由入口
python scripts/install.py --platform both --scope project --project /path/to/my-project --bootstrap

# 仅安装到个人目录
python scripts/install.py --platform both --scope user --bootstrap
```

| 参数 | 含义 |
| --- | --- |
| `--platform` | `codex` / `claude` / `both` |
| `--scope` | `project`（项目内）或 `user`（个人目录） |
| `--dry-run` | 先预览所有将发生的写入 |
| `--force` | 先备份旧版本再替换 |
| `--bootstrap` | 增补/更新 `AGENTS.md` / `CLAUDE.md` 中带标记的路由区块 —— 仅在你显式传入时执行 |

安装器默认拒绝覆盖内容不同的文件。`--bootstrap` 只修改自己带标记的区块，你原有的规则完整保留。建议先跑一次 `--dry-run`。

<details>
<summary><b>路线 B —— 只安装单个 Skill</b></summary>

把 `skills/aletheia/` 复制到目标 Agent 可发现的 Skill 目录：

| Agent | 项目级位置 | 个人级位置 |
| --- | --- | --- |
| Codex | `.agents/skills/aletheia/` | `~/.agents/skills/aletheia/` |
| Claude Code | `.claude/skills/aletheia/` | `~/.claude/skills/aletheia/` |

然后给项目指令加一句：

> 每个实质性任务开始前，先评估已安装的 Skill，用 aletheia 选出、读取并真正应用相关 Skill 后再执行。

</details>

## 透明度实战

一条真实的轨迹，压缩后：

```text
追踪：把季度财报导出为 PDF
考察的 Skill：
  pdf-processing   已选用 —— 负责 PDF 输出
  slides-design    已排除 —— 交付物类型不对
  image-creation   已排除 —— 范围不匹配
操作：
  1. router.py route "把季度财报导出为 PDF"  → pdf-processing (52)
  2. read skills/pdf-processing/SKILL.md     → 214 行
  3. [确认门] 覆盖 Q3-report.pdf（2.1 MB，3 天前修改）？ → 用户选择「另存」
  4. 写入 Q3-report-v2.pdf                 → 12 页，1.8 MB
证据：文件可打开，12/12 页齐全，sha256 已记录
未验证：与原表格的视觉一致性
```

**必须展示被否决的候选。** 只展示你选中的那个，会掩盖最有用的信号 —— 是不是悄悄放过了更好的选项。

### 停顿确认门

```text
此操作将覆盖 Q3-report.pdf（2.1 MB，3 天前修改）。
  1 · 原地覆盖
  2 · 另存为 Q3-report-v2.pdf 并保留两者   ← 推荐
```

确认门触发于：破坏性、对外发送、财务、范围有歧义的操作。
**不**触发于：读文件、搜索、跑测试 —— 什么都问只会训练用户闭眼点同意。

## 管家：由谁来选

安装时**选一次**：

```bash
# 自主（默认）：Aletheia 决定，并展示它否决了什么、为什么
python scripts/install.py --platform both --scope project --bootstrap --mode auto

# 主人驱动：Aletheia 列出带序号的候选，等你回答
python scripts/install.py --platform both --scope project --bootstrap --mode manual
```

无论哪种模式，五阶段披露照旧 —— 手动模式改变的是**谁做决定**，不是**什么必须可见**。

随时切换，不用重装：

```bash
python skills/aletheia/scripts/router.py mode --set manual   # 你接管
python skills/aletheia/scripts/router.py mode --set auto     # 还给它
```

或者说一句：「你自己选」/「我自己选」/「换个状态」。

### 按序号回答

库很大时全列出来没法用，所以先过滤：

```bash
python skills/aletheia/scripts/router.py inventory --query "季度汇报 PPT" --limit 12
```

```text
要用哪些 Skill？回复序号，可以单个、多个（2,5）、all 或 none。

 1. guizang-ppt-skill   可编辑 PPTX 生成
 2. excel-xlsx         表格读写
 3. baoyu-slide-deck   图文排版幻灯片
```

`3` 单选 · `2 5` 多选 · `all` 全选 · `none` 不用 Skill，直接做。
序号是**本次调用有效** —— 装了新东西序号就变，所以每次都重新列，不复用旧序号。

### 到底能扫到几个？

```bash
python skills/aletheia/scripts/router.py inventory --limit 1
```

扫描覆盖个人技能目录**和**嵌套的插件缓存（`<vendor>/<plugin>/<version>/SKILL.md`），
并同时报告「安装总数」和「去重后唯一数」。

`name` 与目录名不一致（市场后缀 `foo__skillhub` 很常见）只报**警告而不丢弃** ——
丢掉就等于让这些 skill 从路由里凭空消失。

## 值得信任的进度条

```text
[████████████░░░░░░░░░░░░]  50%  2/4  → writing report
```

进度条是 Agent 界面里最容易变成谎言的元素。Aletheia 的进度**只是「已完成步骤数 / 声明总步数」**，绝不含估算和推测。

| 状态 | 含义 | 条形表现 |
| --- | --- | --- |
| `working` | 步骤正在推进 | 填充到当前步骤 |
| `blocked` | **正在等你的决定** —— 不是错误 | 填充到停住的位置 |
| `failed` | 无法继续 | 填充到中断的位置 |
| `done` | 全部完成**且已验证** | 满格，`✓ N/total` |

`blocked` 与 `failed` 刻意分开。等确认门是人类参与的正常暂停，把它渲染成错误会
训练用户 panic-click。

```bash
python skills/aletheia/scripts/router.py progress \
  "gather sources" "read SKILL.md" "write report" "verify output" \
  --done 2 --current "writing report"
```

规则：开始前先声明步骤 · 只计已完成步骤 · 在阶段边界更新而不是每条消息 ·
**不存在 ETA 字段** · 100% 意味着已验证 · 小任务直接不显示进度条。

## 真实消耗：只报测得到的数

```bash
python skills/aletheia/scripts/router.py hosts        # 支持哪些宿主
python skills/aletheia/scripts/router.py telemetry    # 各宿主真实用量
python skills/aletheia/scripts/router.py report --out report.html
```

已注册 **12 个主流宿主**。**每个宿主返回相同的字段结构**，读不到的一律标
`unavailable`，**绝不用 0 冒充**。

| 宿主 | 遥测 | 宿主 | 遥测 |
| --- | --- | --- | --- |
| Claude Code | 实测 | OpenCode | 部分（JSON 存储） |
| Codex | 实测 | Droid（Factory） | 实测 |
| Kimi Code | 实测 | Kiro | 实测 |
| Qwen Code | 实测 | Crush | 实测 |
| Gemini CLI | 实测 | Aider | 需开启 |
| Copilot CLI | 实测 | WorkBuddy | 未持久化 |

**每家的字段名都不一样**——Claude 是 `cache_read_input_tokens`，Codex 把
`cached_tokens` 藏在 `input_token_details`，Kimi 是 `message.payload.token_usage`
下的 `input_cache_read`，Qwen/Gemini 用 `promptTokenCount`。适配器靠别名表统一
到一种结构；认不出的格式报 `unavailable`，而不是给一个自信的零。

本机实测：

```text
host                  ok  files  msgs           input      output    cache_read
Claude Code           Y   2      29                58       8,951     2,377,969
Codex                 Y   141    1                180          96            48
Kimi Code             Y   49     3401       8,842,282   1,917,619   359,392,132
Qwen Code             Y   4      106        2,523,460      51,844     2,356,065
Gemini CLI            -   0      -                              unavailable
```

cache read 单独统计而不并入总计——它便宜得多，混在一起成本会错一个数量级。

**明确拒绝估算的三项**：避免选错 skill 重做的节省（需真实 A/B）、用与不用的实际差
（该宿主无遥测）、省钱金额（需单价+实测）。`--actual-tokens` 只能填你从宿主读到的数。

**加一个宿主是改数据不是改代码**：往 `TELEMETRY_HOSTS` 里加一条，然后跑测试。
详见 [`references/MEASUREMENT.md`](skills/aletheia/references/MEASUREMENT.md)。

记录只存在本机 `~/.aletheia/ledger.jsonl`。`report` 导出**自包含** HTML —— 无 CDN、无字体、
无网络，实测值带标记、估算值标 `est`、不可测的格子直接写明原因。见
[`docs/sample-report.html`](docs/sample-report.html)。

### 发不了网址时的交付方式

报告传不上去是**交付问题**，不是「那就将就看吧」的理由。同一份数据三种形态：

```bash
python skills/aletheia/scripts/router.py report --out report.html   # 网页文件，离线可开
python skills/aletheia/scripts/router.py report --out report.md     # issue / PR / 文档
python skills/aletheia/scripts/router.py report --format text       # 聊天窗口 / 终端
```

格式按 `--format` → 输出扩展名 → 默认 HTML 依次判定。不给 `--out` 就直接输出到
stdout，可以直接粘贴。

**文本形态是排好版的文档，不是数据倾倒**：标题分隔线、列对齐、出处图例、
每个数字标注 measured / estimated / unavailable。聊天框里甩一堆裸数字**不在可选范围内**。

## 技能库健康维护

```bash
python skills/aletheia/scripts/router.py audit            # 只报告
python skills/aletheia/scripts/router.py audit --fix      # 修复能确定的损坏
python scripts/daily_check.py                             # 每日体检，只读
```

在真实 300+ skill 的库上，它能发现路由检查永远发现不了的问题：

```text
Library: 550 scanned · 539 healthy · 11 broken (0 need a human) · 10 stale · 216 duplicated
```

`--fix` 会修复超长 `description`、列表式 `allowed-tools`、缺失 frontmatter。
**它绝不删除任何 skill** —— 修不了的会列出来等你决定。陈旧和重复只标记不删除：
留不留是你的判断。

`scripts/daily_check.py` 跑同样的审计加一次遥测采样，写入轮转的本机日志，
只在需要人工判断时才返回非零退出码，方便 Task Scheduler 或 cron 报警。
配置方法见 [`references/MEASUREMENT.md`](skills/aletheia/references/MEASUREMENT.md)。

## 会话级技能作用域

别把整个技能库拖进一个聚焦任务的上下文里：

```bash
# 单次调用
python skills/aletheia/scripts/router.py route "做一份 PPT" --root skills --only slides-design

# 整个会话 —— 在项目根放 aletheia-session.json
{ "only": ["slides-design", "image-creation"] }
```

`--only` 优先于清单文件；两者同时存在时取交集。被抑制的技能会在输出里以
`suppressed_skills` 明确列出，不会静默丢弃。作用域是**路由过滤器，不是安全边界**。

## 上下文压力监测

```bash
python skills/aletheia/scripts/router.py context \
  --transcripts ~/.workbuddy/workspace/sessions --host workbuddy
```

| 状态 | 估计占用 | 动作 | Claude Code | Codex | WorkBuddy |
| --- | --- | --- | --- | --- | --- |
| `ok` | <70% | 继续 | — | — | — |
| `notice` | 70–85% | 先压缩再继续 | `/compact` | `/compact` | `/compact` |
| `trim` | 85–100% | 立即压缩 | `/compact` | `/compact` | `/compact` |
| `new_session` | ≥100% | 交接后开新会话 | `/clear` | `/new` | `/new` |

> **诚实声明。** 除非宿主提供真实的 token 遥测，否则本命令会返回
> `is_measured_context_percentage: false`。该数字是基于磁盘 transcript 字节数、
> 相对一个假定窗口估算出来的。Aletheia 绝不把估算包装成实测。

切换会话前先写交接摘要：当前目标、已完成步骤、关键结论、未解决问题、涉及的文件路径。

## CLI

```bash
# 全量清点（带序号，可过滤）
python skills/aletheia/scripts/router.py inventory --query "pdf" --limit 20

# 由谁选择：查看，或切换并持久化
python skills/aletheia/scripts/router.py mode
python skills/aletheia/scripts/router.py mode --set manual

# 发现约定目录中的技能
python skills/aletheia/scripts/router.py scan --json

# 带理由的候选召回
python skills/aletheia/scripts/router.py route "分析这个表格" --top 5

# 校验技能树的 frontmatter
python skills/aletheia/scripts/router.py lint --root skills

# 对内置 fixture 跑离线召回评测
python skills/aletheia/scripts/router.py eval --root tests/fixtures --cases tests/eval_cases.json

# 会话级作用域
python skills/aletheia/scripts/router.py route "做一份 PPT" --root skills --only slides-design

# 上下文压力
python skills/aletheia/scripts/router.py context --transcripts <dir> --host claude

# 进度条
python skills/aletheia/scripts/router.py progress "read" "write" "verify" --done 1

# 单元测试
python -m unittest discover -s tests -v
```

`route` 绝不执行被发现的 Skill。`score` 是人工设计的排序信号 —— 不是概率、
不是成功率、也未经统计校准。请先读候选的 `SKILL.md` 再决定。

## 项目结构

```text
.
├── skills/aletheia/
│   ├── SKILL.md                   # 规范入口
│   ├── scripts/router.py          # 只读发现、作用域、lint、eval、context、进度
│   └── references/                # TRANSPARENCY · PROGRESS · BUTLER · MEASUREMENT · ROUTING_POLICY · SECURITY · CONTEXT · EXAMPLES
├── prompts/MASTER_PROMPT.zh-CN.md # 完整常驻提示词（中文）
├── prompts/MASTER_PROMPT.en.md    # 完整常驻提示词（英文）
├── scripts/install.py             # 非破坏式安装器
├── scripts/daily_check.py         # 每日体检（默认只读）
├── examples/                      # 会话作用域清单示例
├── tests/                         # 单元测试、fixtures、双语评测案例
├── docs/                          # ARCHITECTURE · EVALUATION · RELEASE_CHECKLIST
└── .github/workflows/ci.yml       # Python 3.10 / 3.12 / 3.13
```

## 设计原则

- **遵循规范而非私有格式** —— 标准的 `SKILL.md` + `references/` + `scripts/`
- **两级发现** —— 先宿主技能清单，后本地元数据
- **人机分工** —— CLI 提高召回率与可审计性；语义决策、授权与执行归 Agent
- **诚实遥测** —— 估算永远标注为估算
- **低上下文成本** —— 元数据先行，只在选中时才读全文
- **安全默认值** —— 只扫一层、拒绝符号链接、不执行任何代码

## 诚实的边界

**没有任何普通 SKILL.md 或系统提示词能保证每条请求都正确调用 Skill。**
Aletheia 能提高命中率与可审计性，但前提是目标 Agent 确实能访问那些 Skill
和工具。CLI 只是只读候选召回器，不替代宿主的 Skill API、权限或执行器。
目前还没有经过验证的公开基准 —— 内置 fixtures 是冒烟测试，不是准确率声明。

## 常见问题

**为什么不扫描电脑上所有文件夹？**
全盘递归不安全、性能差，且会引入大量与当前运行时无关的 Skill。只扫描宿主已注册、
用户指定或约定目录。

**能自动调用插件/云端 Skill 吗？**
只有宿主同时暴露技能列表和真实调用接口才行。文件扫描替代不了插件接口。

**`--bootstrap` 会覆盖我的 AGENTS.md 吗？**
不会，它只增补/更新自己带标记的区块。先跑 `--dry-run` 看清楚会改什么。

**高分是不是就代表可以直接用？**
不是。分数只是词面排序信号，没有概率含义、未经校准。请先读候选的 `SKILL.md` 再判断。

## 参考

- [Agent Skills 开放规范](https://agentskills.io/specification)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [OpenAI API Skills](https://developers.openai.com/api/docs/guides/tools-skills)
- [OpenAI skills 示例](https://github.com/openai/skills)

## 许可

MIT —— 见 [LICENSE](LICENSE)。
欢迎贡献：[CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md)
