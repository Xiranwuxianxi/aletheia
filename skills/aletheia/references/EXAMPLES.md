# Routing examples

**User:** 帮我把这份 PDF 逐页提取并汇总。  
**Approach:** Determine whether a PDF-specific skill is installed; load it before extracting. If it includes images, use its page-image workflow. Return the requested summary and note verified extraction quality.

**User:** 给我分析这个 Excel，然后做一套汇报 PPT。  
**Approach:** Select spreadsheet/data analysis for source calculations, then presentation for deck authoring. Don't substitute a screenshot for an editable deck.

**User:** 你帮我把这句话翻译成英语。  
**Approach:** Use a relevant installed translation skill if one exists and materially improves output; otherwise translate directly. No compulsory filesystem scan or invented invocation.

**User:** 请审计我的 Agent Skills 是否会被遗漏。  
**Approach:** Use read-only `scan` and `lint`, compare metadata coverage, inspect known misses with test cases, report whether the test measures recommendation or true invocation.

**User:** 请发布生产环境最新代码。  
**Approach:** Even if deployment skill matches, check authorization, repository scope, environment constraints, operational safety, and approval. No routing result itself authorizes deployment.

**User:** 总结这个网页，并验证论文出处。  
**Approach:** Use an installed research/browsing skill if available, retrieve actual page, verify the cited paper from authoritative sources, and make no unsupported claims.
