## Agent skills

### Issue tracker

Issues are tracked as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix), recorded as `Status:` lines. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Coding style
- Choose the simplest solution that works. No abstractions, helpers, classes, or new files for one-off operations.
- Implement only what was asked. No extra features, config options, or defensive error handling for cases that can't happen.
- Prefer the standard library and existing tools over custom scripts.
- For non-trivial changes, state the approach in 1-2 sentences before writing code.