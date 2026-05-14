# Mapping Rulebook Working Style

This document captures the intended coding style for the active `logic/mapping_rulebook/` system so future edits stay aligned with how the project is being built.

---

## Core Style

- Keep stage modules simple and easy to inspect.
- Prefer small functions that operate on one file or one logical item at a time.
- Let stage modules fail hard when an assumption is broken.
- Avoid silent fallbacks inside the core stage logic.
- Delay heavy abstraction until the workflow shape is stable.

The goal is not defensive cleverness. The goal is high visibility into what the pipeline is doing so issues are easy to notice and debug.

---

## Module Pattern

The preferred pattern in this repo is:

1. Write the reusable logic as small functions.
2. Keep those functions focused on a single unit of work.
3. Use the `if __name__ == "__main__"` block as a temporary manual harness while the stage is being developed.
4. Move cross-file orchestration into a dedicated runner later, once the stage behavior is stable.

This means some scripts will intentionally look like:

- reusable logic in the main functions
- a manual one-file or batch test harness at the bottom
- no attempt to make the stage entrypoint look production-finished before the runner exists

That is intentional.

---

## Fail-Hard Rule

For the active mapping pipeline, "fail loudly" is preferred over "continue with best effort" inside the core stage modules.

Examples:

- missing expected files should stop the stage
- broken schema assumptions should stop the stage
- unexpected data shape should stop the stage
- incorrect configuration should be made obvious quickly

The reason is simple: silent continuation can hide accounting or mapping mistakes that later show up as bad NOI verification.

---

## Rulebook Testing Style

The documented target architecture still treats rulebook v2 as the preferred end-state, but runtime testing can switch between v1 and v2 through `config/rulebook_runtime.py`.

For A/B verification, change the active rulebook profile in that config file instead of comment/uncommenting imports across multiple scripts.

Keep the rulebook choice aligned across every affected stage, especially:

- `pipeline/1_mapping/map_blocks.py`
- `pipeline/1_mapping/find_mapping.py`
- `pipeline/0_build_rulebook/category_config.py`
- `pipeline/utils/convert_rulebook_to_excel.py`

Future runners can parameterize this further. For now, one central config switch is the intended workflow.

---

## Pipeline Layout

The numbered folder structure is intentional:

- `0_build_rulebook/`
- `1_mapping/`
- `2_noi_verification/`

The numbers are part of the project language. They make the pipeline order obvious and should be preserved.

Likewise, dated outputs under `output_docs/<YYYY_MM_DD>/` are intentional because they make audits and reruns easier to reason about.

---

## Documentation Expectations

When active behavior changes, update the docs that explain the current system:

- `docs/README.md` for overview and run flow
- `docs/CONTEXT.md` for folder structure, contracts, and script inventory
- `docs/LOGIC.md` for algorithm behavior
- `docs/DECISIONS.md` for short design decisions and rationale
- `docs/audits/` for dated system-state snapshots

The purpose is to preserve system context even when chat history is gone.
