# Engine Scale Program — Agent prompts

**Start here:** `../2026-06-10-engine-scale-program.md`

## Execution order

1. **Wave 0** — `PROMPT_WAVE_0_PLANNING.md` (Planning mode only)
2. Human reviews specs + approves Wave 1
3. **Wave 1–4** — use generated `PROMPT_WAVE_*` files from Wave 0 output
4. One PR per wave on branch `program/engine-scale-wave-N`

## Do not

- Run all waves in one agent session
- Merge without CI + evidence links in PR body
- Promote challenger to champion without human approval
