# Security Policy

This is a private Dijital Team repository. It integrates with production systems
(Lever, BambooHR, and — later — Microsoft Entra, HubSpot, Microsoft Graph), so
credential hygiene is a hard requirement, not a guideline.

## Reporting a vulnerability or a leaked secret

Do **not** open a public issue or PR. Contact the repository owner
(`@IMWeeriyasinghe`) directly and privately. If a credential has been exposed,
report it immediately — rotation comes first, investigation second.

## Secret-handling rules (see also CLAUDE.md §60, §73)

- Real credentials live **only** in an untracked `apps/<service>/.env` file.
- They are never placed in tracked files, `.env.example`, commit messages, test
  fixtures, logs, screenshots, or documentation.
- `.env.example` files contain only empty values or clearly-labelled
  `dev-only-…-change-me` placeholders.
- Front-end code never receives secrets; the web apps have no environment files
  and call same-origin relative paths only.
- The Lever API key is currently **read-only** by contract — see CLAUDE.md §60.

## Layers that enforce this

1. `.gitignore` — `.env.*` (except `*.env.example`), plus `*.pem`/`*.key`/`*.pfx`/
   `*.p12`/`serviceAccount*.json`/`secrets.json`.
2. Local `gitleaks` pre-commit hook (`.pre-commit-config.yaml`).
3. `secret-scan` GitHub Actions workflow on every push and pull request.

## If a secret is committed

1. **Rotate the credential now** in the upstream system (Lever / BambooHR / Entra
   / etc.). Assume it is compromised.
2. Purge it from history with `git filter-repo` (or the GitHub-recommended BFG),
   then force-push and have every clone re-clone.
3. Confirm the `secret-scan` workflow is green on the rewritten history.
4. Record the incident and the rotation date with the repository owner.
