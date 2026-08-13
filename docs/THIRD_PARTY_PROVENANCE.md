# Third Party Provenance

## Source Repository
**Repository:** `cobusgreyling/loop-engineering` (GitHub)
**Commit SHA:** `01f88a5fb5941a1ddb1b31a923854f8873138f2a`
**Retrieval Date:** 2026-07-25
**License:** MIT License (verified via `LICENSE` file)

## Components Adopted for GreenLead

| Component | Upstream Source Path | Adoption Type | Notes |
|-----------|-----------------------|---------------|-------|
| `STATE.md` | `starters/minimal-loop/STATE.md.example` | Adapted | Modified for GreenLead Phases and Git constraints. |
| `LOOP.md` | `LOOP.md` | Adapted | Stripped L2/L3 automation; mapped strictly to Antigravity Planning Mode. |
| `loop-budget.md` | `loop-budget.md` | Adapted | Defined Antigravity-specific attempt limits. |
| `loop-constraints.md`| `loop-constraints.md` | Adapted | Constraints localized to GreenLead workspace. |
| `loop-run-log.md` | `loop-run-log.md` | Copied | Empty initialized log. |
| `gate.yaml` | `gate.yaml` | Adapted | Locked down to Phase 1 allowed paths. |
| `loop-triage` | `templates/SKILL.md.loop-triage` | Adapted | Ported to Antigravity SKILL format (L1 Report-only). |
| `minimal-fix` | `starters/pr-babysitter/` (conceptual) | Locally Written | Antigravity local adaptation inspired by upstream L2 isolation. |
| `loop-verifier` | `docs/primitives.md` (Checker pattern)| Locally Written | Antigravity specific Verification loop. |

## Global Skills Audit
The directory `C:\Users\bahaa\.gemini\config\skills\loop-engineering\` was a direct `Copy-Item` dump of the repository. While `.git` exists and it is at commit `01f88a5`, the Antigravity `SKILL.md` injected inside it is merely a summary overlay. The npm dependencies are **not** installed. Executable scripts are **not** ready or verified in this environment.

**Status:** UNVERIFIED THIRD-PARTY CONTENT
**Action Required:** Global directory should be reset or ignored. All execution logic will remain local to `.agents/skills` inside the GreenLead workspace.
