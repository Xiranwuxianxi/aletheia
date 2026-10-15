# The butler: knowing the whole library

Aletheia manages the **entire installed skill library**, not a hand-picked
subset. A butler who does not know what is installed cannot route honestly.

## Measured inventory (this machine)

| Metric | Count |
| --- | --- |
| Installed skill directories | 298 |
| **Unique skills** | **233** |
| Duplicate installs (personal + plugin) | 65 |
| Reachable by routing before this fix | 186 |
| Unreachable plugin skills now found | ~47 |

Check your own machine at any time:

```bash
python scripts/router.py inventory --limit 1
```

`installed` counts every `SKILL.md` found; `unique_skills` collapses copies of
the same skill name. **Duplicate installs are normal** — the same skill often
exists both in `~/.workbuddy/skills/` and in a plugin cache.

## Why the old number was wrong

Discovery originally walked exactly one directory level. That silently missed
every plugin-cache layout of the form
`cache/<vendor>/<plugin>/<version>/SKILL.md`, which is **three** levels deep. On
this machine that hid roughly 47 skills the host could use but the router could
never see. Discovery is now depth-3 and still bounded — no unbounded
recursion, symlinks still refused.

The same fix applies to your own layout: if your skills live deeper than one
level, they were invisible.

## Warnings do not remove skills

The Agent Skills spec requires `name` to match the parent directory. Real
installs break this constantly:

```text
name 'alice-fund-compare' vs directory 'alice-fund-compare__skillhub'
name 'wechat-cover'      vs directory 'explosive-cover-generator-gzh'
name 'frontend-dev'      vs directory 'skill_2052764137292271616'
```

Dropping these would hide **27 skills — a seventh of the personal library** —
from routing, for a naming detail that does not affect usability. So a name/dir
mismatch is now a **warning**, and the skill stays in the registry with its
declared name.

`lint --strict` still fails on them, which is what you want when validating a
skill you are publishing.

## Who chooses

The owner decides the operating mode **once**, at install:

```bash
python scripts/install.py --platform both --scope project --bootstrap --mode auto    # default
python scripts/install.py --platform both --scope project --bootstrap --mode manual
```

| Mode | Behaviour |
| --- | --- |
| `auto` | Aletheia chooses, then discloses the pick, the rejects and the reasons |
| `manual` | Aletheia presents numbered candidates and waits |

The bootstrap block records the mode, so it survives across sessions without
re-asking. Switch any time — one sentence, no reinstall:

- "你来选" / "switch to auto"
- "我自己选" / "switch to manual"
- "换个状态" → show current mode and both options

State file:

```bash
python scripts/router.py mode                    # read
python scripts/router.py mode --set manual       # write
python scripts/router.py mode --set auto
```

## Manual mode: answer by number

With 233 skills installed, listing all of them would be unusable and expensive.
Always filter first:

```bash
python scripts/router.py inventory --query "quarterly earnings deck" --limit 12
```

```text
Which skills should I use? Reply with a number, several (2,5), 'all', or 'none'.

 1. guizang-ppt-skill   editable PPTX generation
 2. excel-xlsx         spreadsheet read/write
 3. baoyu-slide-deck   image-rich slide decks
```

Accepted answers:

| Reply | Meaning |
| --- | --- |
| `3` | Single selection |
| `2 5` or `2,5` | Multiple selection |
| `all` | Everything listed |
| `none` | No skill — do the task directly with ordinary tools |
| a name | Direct pick, when the owner knows it |

**Numbers are per-invocation.** After any install, removal or refresh they
change. Never reuse numbers from an earlier list; re-run `inventory` and show
the fresh list.

## What the butler still will not do

- **Read every SKILL.md.** Knowing a skill exists costs one description line;
  loading its body costs thousands of tokens. Metadata first, body on selection.
- **Pretend an unread skill was used.** Inventory presence is not invocation.
- **Override the host.** If the host mandates a domain skill, that runs; scope
  and mode govern *routing*, not permissions.
- **Guess at numbers.** If a number is out of range or ambiguous, re-list rather
  than inferring what the owner meant.

## Related

- `SCOPE_CONTROL.md` — narrowing the visible set to save context
- `TRANSPARENCY.md` — what must be disclosed in either mode
- `PROGRESS.md` — reporting progress on a long task
