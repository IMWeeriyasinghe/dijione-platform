## What & why

<!-- Short description of the change and the reason for it. Link any issue. -->

## Checklist

- [ ] Commits follow Conventional Commits (`feat(scope): …`, `fix(scope): …`, …)
- [ ] `npm -w apps/<app> run lint` and `... run build` pass for touched web apps
- [ ] `ruff check .` and `pytest -q` pass for touched API services
- [ ] `alembic upgrade head` runs clean if migrations changed
- [ ] **`.env.example` updated** for any new `Settings` field (same PR)
- [ ] No `.env`, `*.db`, key material, or secret is staged
- [ ] Docs updated (`docs/…`, `README.md`, `CLAUDE.md`) if behaviour changed
