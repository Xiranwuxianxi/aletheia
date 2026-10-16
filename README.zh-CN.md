<div align="center">

# Α Aletheia

**让 Agent 技能路由不再黑箱。**
*把任务交给对的 Skill —— 并把整个过程摊开给你看。*

[![License: MIT](https://img.shields.io/badge/license-MIT-534AB7?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-1D9E75?style=flat-square)](https://www.python.org/)
[![Agent Skills](https://img.shields.io/badge/spec-Agent%20Skills-BA7517?style=flat-square)](https://agentskills.io/specification)
[![Version](https://img.shields.io/badge/version-1.10.0-888780?style=flat-square)](CHANGELOG.md)

[English](README.md) · **简体中文**

</div>

---

Aletheia（Ἀλήθεια，希腊语）的原意是**「解蔽」**——真理即是**未被遮蔽**之物。它正是「黑箱」的反义词，而这也正是本项目要解决的问题：Agent 悄悄选了个 Skill、悄悄跑完、给你一个你无法审计的结果。

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
| WorkBuddy | `.workbuddy/skills/aletheia/` | `~/.workbuddy/skills/aletheia/` |
| Hermes | — | `~/.hermes/skills/aletheia/` |
| OpenClaw | — | `~/.openclaw/skills/aletheia/` |
| Kimi Code | — | `~/.kimi/skills/aletheia/` |
| Qwen Code | — | `~/.qwen/skills/aletheia/` |
| Gemini CLI | — | `~/.gemini/extensions/aletheia/` |
| GitHub Copilot CLI | — | `~/.copilot/skills/aletheia/` |

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

## Windows / macOS / Linux 都能跑

纯标准库，**三个平台都不需要装任何东西**（macOS 和 Linux 自带 `python3`）。
真正存在的差异是显式处理的，不是靠假设：

| 关注点 | Windows | macOS / Linux |
| --- | --- | --- |
| 换行符 | 修复后保留 CRLF | 保留 LF |
| 路径分隔符 | `\` 和 `/` 都接受 | `/` 是原生；`\` 只是文件名字符 |
| 家目录 | `Path.home()` → `%USERPROFILE%` | `$HOME` |
| sqlite 锁 | 拆目录前先关连接 | 咨询锁 |
| 终端字形 | ASCII 进度条兜底 | 方块字符进度条 |

其中**两个是真 bug，而且是 CI 发现的**——在开发者本机上完全看不出来：

- **修复时 CRLF 被静默丢掉。** Python 文本模式读取时会把 CRLF 转成 LF，这让所有比较都不受
  CRLF 影响，但也**抹掉了「这个文件用的是什么换行符」的证据**。结果修复后的文件总是变成 LF，
  在 Windows 上显示为整文件 diff。
- **零依赖路径与 PyYAML 路径结论不一致。** 列表式 `allowed-tools` 在没有 PyYAML 时被判成
  `invalid_yaml`，有 PyYAML 时判成 `allowed_tools_list`——于是本机绿、CI 红。现在有独立 job
  只用标准库跑全套检查，还有一道结构性守卫：任何涉及路径分隔符的测试**必须**分支 `os.name`。

零依赖这个承诺是**有实际价值的**：它让 Aletheia 能跑在全新的 CI 容器里、另一个 agent 的沙箱里、
或者任何没有包管理器的机器上——而那恰恰是路由工具最该能用的地方。

```bash
# 自证：屏蔽 PyYAML 后跑同一套检查
python tests/zero_dependency_check.py
```

该脚本对无 PyYAML 路径断言 13 项，CI 也把它作为独立 job 运行。
它存在的理由是：**「零依赖」这个承诺，会在第一次有人顺手 import 一个方便库时无声地失效**。

## 本机实测数据

| 指标 | 数量 |
| --- | --- |
| 可见的唯一 skill | **252** |
| 扫描到的安装位置 | 960 |
| 已注册 agent 宿主 | 14 |
| 实测到 token 遥测的宿主 | 4 |

开发过程中同一台机器先后报出 186 → 233 → 252 个唯一 skill，**每一次跳升都对应一个真实缺陷**：
先是一层扫描漏掉嵌套的插件缓存，再是各宿主的 skill 目录压根没被扫过。每一段的原因都记在
`CHANGELOG.md` 里。

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

已注册 **14 个主流宿主**。**每个宿主返回相同的字段结构**，读不到的一律标
`unavailable`，**绝不用 0 冒充**。

| 宿主 | 遥测 | Skill 目录 | 宿主 | 遥测 | Skill 目录 |
| --- | --- | --- | --- | --- | --- |
| Claude Code | 实测 | `.claude/skills` | **OpenClaw** | SQLite | `.openclaw/skills` |
| Codex | 实测 | `.agents/skills` | **Hermes Agent** | SQLite | `.hermes/skills` |
| Kimi Code | 实测 | `.kimi/skills` | OpenCode | JSON 存储 | `.opencode/skills` |
| Qwen Code | 实测 | `.qwen/skills` | Factory Droid | 实测 | `.factory/skills` |
| Gemini CLI | 实测 | `.gemini/extensions` | Kiro | 实测 | `.kiro/skills` |
| GitHub Copilot CLI | 实测 | `.copilot/skills` | Crush | 实测 | `.crush/skills` |
| Aider | 需开启 | `.aider/skills` | WorkBuddy | 未持久化 | `.workbuddy/skills` |

**每家的字段名都不一样**——Claude 是 `cache_read_input_tokens`，Codex 把
`cached_tokens` 藏在 `input_token_details`，Kimi 是 `message.payload.token_usage`
下的 `input_cache_read`，Qwen/Gemini 用 `promptTokenCount`。适配器靠别名表统一
到一种结构；认不出的格式报 `unavailable`，而不是给一个自信的零。

**SQLite 类宿主**（OpenClaw、Hermes）直接读库——Python 的 `sqlite3` 是标准库，
**不引入任何依赖**；且以 **URI `mode=ro` 只读打开**，因为遥测读取器绝不能改或锁住宿主的库。

**加宿主是改数据不是改代码**：往 `TELEMETRY_HOSTS` 加一条，然后跑测试。详见
[`references/MEASUREMENT.md`](skills/aletheia/references/MEASUREMENT.md)。

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

### 一套库，多个 agent

不同 agent 把 skill 放在不同目录。Aletheia 知道每个受支持宿主的目录在哪，所以
**装在任何 agent 下的 skill 都仍然可达**：

```text
~/.workbuddy/skills        ~/.hermes/skills        ~/.openclaw/skills
~/.claude/skills           ~/.agents/skills         ~/.copilot/skills
~/.kimi/skills             ~/.qwen/skills           ~/.gemini/extensions
~/.factory/skills          ~/.kiro/skills           ~/.crush/skills
~/.aider/skills            ~/.config/opencode/skill
```

这比听起来更重要。**库在多个 agent 间镜像，必然产生重复和漂移**——而审计会直接告诉你，
不会藏着：

```bash
python skills/aletheia/scripts/router.py audit \
  --root ~/.hermes/skills --root ~/.openclaw/skills --unused-days 30
```

```text
scanned 213 skill(s)
healthy 210   broken 3 (blocking 0)   stale 2   duplicated 17
```

inventory 按名字去重，所以你回答的序号**永远不会指向一对歧义项**——但**重复安装的数量
会如实报出来**，因为那才是值得处理的事。

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

## 不依赖宿主的自主计量

读宿主「愿意导出的数据」是被动的。`estimate` 反过来——**自己扫本机，能测多少测多少，
不向任何人索要**：

```bash
python skills/aletheia/scripts/router.py estimate --task "季度 PPT"
python skills/aletheia/scripts/router.py estimate --only excel-xlsx,guizang-ppt-skill
```

```text
input 11,365,980 · output 1,978,510 · cache_read 364,126,214 · cache_write 483,380
completeness: partial — 10 个宿主未持久化 token 计数
library: 252 个唯一 skill（708 处重复安装）
context cost: 44,322 est. tokens 元数据
```

有两项**明确标 `unavailable` 而非估算**：**宿主内部推理 token**（根本没落盘）、
**计费金额**（需要模型 id + 价格表）。**不内置价格表**——过期价格表会悄悄变成一个
自信的、错误的金额。

宿主日志增长按**字节**报告，**明确标注不是 token**，也**绝不并入 token 总计**。

作用域省多少，是**从文件实测**而非建模估算：

```text
全库:  44,322 est. tokens 元数据
限 2 个:   347 est. tokens        —— 省 99.2%
```

## 知道什么时候有更新

```bash
python skills/aletheia/scripts/router.py update          # 自己是不是最新版？
python skills/aletheia/scripts/router.py update --scan   # 其他 skill 呢？
python skills/aletheia/scripts/router.py update --no-fetch   # 离线：只看本地状态
```

```text
local_version 1.9.0 · local_tag v1.9.0 · branch main
latest_tag    v1.9.0 · update_available false
```

有新版时会告诉你变了什么，**然后停下**：

```text
UPDATE AVAILABLE: v1.9.0 -> v1.10.0
落后 3 个 commit
  45209d4 修复中文 README、重复的 CHANGELOG 条目、陈旧缓存
  ...
```

### 只检测，绝不自动改

**没有 `--apply`，而且有测试强制这一点。**
改写一个别的 agent 正在读的 `SKILL.md` 是笔糟糕的买卖——读的人会拿到写了一半的文件，
而你并没有要求承担这个风险。命令把决定权交回给你：

```bash
git log HEAD..origin/main --oneline    # 先看清楚改了什么
git pull --ff-only origin main
python -m unittest discover -s tests   # 验证后再信任
```

### 更新检测依赖 tag，所以仓库补齐了 tag
比版本需要可比对的锚点。`v1.8.0` 到 `v1.9.0` 都已打 tag，
并且有测试在当前版本未打 tag 时失败——**一个不能自我检测更新的可发布仓库是矛盾的**。

### 大部分 skill 没有上游记录，而它如实这么说

```bash
python skills/aletheia/scripts/router.py update --scan
```

```text
252 个唯一 skill · 2 个有 git 上游 · 250 个无记录
```

这是一个普通技能库的真实状态：被丢进 `~/.agents/skills/` 的 skill 没有来源记录，
所以**没有任何东西能替它检查更新**。扫描如实报出这个缺口，而不是猜一个 URL。
**250 个没有来源记录的 skill 是一个发现，不是 bug**——它告诉你哪些会悄悄变陈旧。

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

作用域可以来自多个来源——`--only`、会话清单文件、`--profile`。
**同时存在多个来源时取交集，不是覆盖**：只有每个来源都点名的技能才算在作用域内。
被抑制的技能会在输出里以
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
python skills/aletheia/scripts/router.py scan

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

所有子命令**一律向 stdout 输出 JSON** —— 没有 `--json` 参数，因为不存在其他格式。
失败时输出 `{"error": "..."}` 并以 `2` 退出。
argparse 仍负责真正的参数解析错误（未知子命令、缺参数），因为那发生在命令语义之前，
用它的用法提示才对。

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
