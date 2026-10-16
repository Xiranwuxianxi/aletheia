# 任务：Aletheia v1.9.0 遗留问题修复

## 背景

仓库：`E:\skill的自动路由skilllinghaiSKill`，当前版本 v1.9.0，分支 `main`，工作区干净。
项目是一个 skill 自动路由工具，核心为 `skills/aletheia/SKILL.md`（路由协调指令）+
`skills/aletheia/scripts/router.py`（约 3000 行 CLI，stdlib-only，PyYAML 为可选 extra）。
验证命令：

```bash
python -m unittest discover -s tests -v
python skills/aletheia/scripts/router.py lint --root skills
python skills/aletheia/scripts/router.py eval --cases tests/eval_cases.json --root tests/fixtures
```

要求：全部修改完成后，lint 必须 `ok: true`，eval 必须 16/16 通过，单元测试在 Linux/macOS 全过、
Windows 下除被显式 skip 的用例外全过。不要改动任何既有测试的语义断言；不要引入新的第三方依赖。

## 修复项（按优先级）

### P0-1 Windows 符号链接测试失败
- 现象：`tests/test_router.py:49` `test_malformed_and_symlink_guard` 在无特权的 Windows 上抛
  `OSError: [WinError 1314] 客户端没有所需的特权`（创建符号链接需管理员或开发者模式）。
- 要求：在测试内探测符号链接能力（尝试创建临时 symlink，捕获 OSError 后 `self.skipTest(...)`），
  使该用例在无权限环境自动 skip 而非 error。同时在 `.github/workflows/ci.yml` 的矩阵中加入
  `windows-latest`（如已有矩阵则追加），确保 CI 能覆盖此路径。

### P0-2 「overrides / intersect」矛盾表述（三处）
- 代码事实：`router.py` 中 `--only` 与 session manifest 同时存在时取**交集**。
- 需修正为「取交集」统一表述的位置：
  - `skills/aletheia/SKILL.md:182`（现为 "`--only` overrides the others; all sources present means intersect."）
  - `README.md:459`（现为 "`--only` overrides the manifest; both present means intersect."）
  - `README.zh-CN.md:415`（现为「`--only` 优先于清单文件；两者同时存在时取交集。」）
- 三处改为语义一致的无歧义表述，例如："Multiple scope sources are intersected when more than one is present."
  中文版对应翻译。修改前先 grep 确认无第四处同款表述。

### P1-1 CLI 错误输出协议统一
- 现状：`router.py` 中两种失败输出并存——`parser.error()`（stderr + exit 2，见约 2876/2935/2944/2949 行）
  与 JSON `{"error": ...}` + `return 2`（见约 2864/2873/2896 行）。行号可能漂移，以实际搜索为准。
- 要求：统一为 JSON `{"error": ...}` 到 stdout + 退出码 2（与 scan/route/lint 的 JSON 输出契约一致），
  使机器消费方只需处理一种协议。argparse 层面的参数解析错误（如未知子命令）可保留 parser 默认行为，
  但业务逻辑错误必须走 JSON 路径。同步更新 README 中关于退出码/错误格式的描述（如有）。

### P1-2 `--json` 死参数
- 现状：`router.py` 约 2610 行给 scan/route/lint 定义了 `--json`，但这两个子命令无条件输出 JSON
  （约 2957 行），flag 从未被消费。
- 要求：二选一——(a) 移除 scan/route/lint 的 `--json` 参数并在 help/文档中注明 JSON 是唯一输出格式；
  或 (b) 实现 `--json` 的实际分支（如默认人类可读输出、`--json` 时输出 JSON）。
  优先选 (a)，改动面最小且符合现状契约。无论选哪个，README 中的 CLI 说明必须与实际行为一致。

### P2-1 README.zh-CN.md 病句
- 第 19 行：「Aletheia（Ἀλήθεια，希腊语）是**「解蔽」** principles——真理即**未被遮蔽**之物」，
  "principles" 漏翻、语法断裂。重写为通顺的中文（可参考 README.md 对应英文段落的本意）。

### P2-2 CHANGELOG 重复条目
- 「README FAQ rendered literal `\n`…」同时出现在 1.1.0 Fixed（约 514 行，已标注 `(1.0.0)`）和
  1.0.0 Fixed（约 551 行）。保留 1.0.0 的原始记录，从 1.1.0 中删除重复条目（若该重复意在说明
  回归修复，则改写为明确的回归修复措辞，而非原样重复）。

### P2-3 __pycache__ 清理
- 删除 `skills/aletheia/scripts/__pycache__/` 与 `tests/__pycache__/` 残留（`.gitignore` 已覆盖，
  仅清理磁盘）。

## 约束

1. 不改动 `router.py` 的路由/匹配算法语义（域别名、阈值、权重常量一律不动）。
2. 版本一致性测试（pyproject / SKILL.md / CHANGELOG / README 徽章四处 1.9.0）必须保持通过；
   本次修复不发新版，不改版本号，除非修复项本身要求。
3. README.md 与 README.zh-CN.md 的任何 CLI/行为描述修改必须双语同步。
4. 完成后运行三条验证命令并贴出结果；Windows 环境注意 symlink 测试应显示 skip 而非 error。
5. 提交信息按仓库既有风格（参考 `git log --oneline`），一个逻辑修复一个 commit。
