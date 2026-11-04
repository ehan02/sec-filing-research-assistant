# Coding standards

Applied at review. Ruff (`pyproject.toml`) covers the mechanical rules; these are the judgement calls.

- Choose the simplest solution that works. No abstractions, helpers, classes, or new files for one-off operations.
- Implement only what was asked. No extra features, config options, or defensive error handling for cases that can't happen.
- Prefer the standard library and existing tools over custom scripts.
