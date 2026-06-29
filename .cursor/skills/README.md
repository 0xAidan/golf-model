# Project Cursor Skills

Bundled skills from [awesome-cursor-skills](https://github.com/spencerpauly/awesome-cursor-skills) (MIT-style curated list). Each subdirectory contains a `SKILL.md` discovered automatically by Cursor agents in this repo.

**Source commit:** cloned from `https://github.com/spencerpauly/awesome-cursor-skills` (main).

**Count:** 65 skills in `.cursor/skills/*/SKILL.md`.

## How agents use these

1. Read `SKILL.md` in the relevant directory when the task matches the skill description.
2. For the Golf Model upgrade program, follow the wave → skill map in `.cursor/plans/golf-model-master-upgrade-plan-prompt.md`.
3. Prefer project skills here over improvising workflows.

## External skills (not vendored — install separately if needed)

Listed in awesome-cursor-skills README but hosted in other repos:

| Skill | Source |
|-------|--------|
| vercel-react-best-practices | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) — also via Cursor Vercel plugin |
| shadcn-ui | [ui.shadcn.com/docs/skills](https://ui.shadcn.com/docs/skills) — also via Cursor Figma/Vercel plugins |
| mattpocock-tdd, prd-to-issues, improve-architecture, grill-me | [mattpocock/skills](https://github.com/mattpocock/skills) |
| sentry-* skills | [getsentry/skills](https://github.com/getsentry/skills) |
| anthropic-* skills | [anthropics/skills](https://github.com/anthropics/skills) |

Cursor built-in / plugin skills (cursor-team-kit, compound-engineering, etc.) remain available globally and are referenced in the master plan prompt.

## License

Skills are third-party content from their respective repositories. See awesome-cursor-skills [CONTRIBUTING.md](https://github.com/spencerpauly/awesome-cursor-skills/blob/main/CONTRIBUTING.md) and each skill's source repo for license terms.
