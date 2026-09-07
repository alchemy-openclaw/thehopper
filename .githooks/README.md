# pre-push guard

Blocks pushes containing machine artifacts or secrets. Written Sep 2026 after
three pushes from MikeM's Mac swept in `backend/venv/` (macOS binaries),
`frontend/node_modules/`, a **0-byte `backend/thehopper.db` blob** (git's
refuse-to-overwrite-untracked check was all that saved the 24MB live prod DB
during the deploy pull), and `.env` exposure risk (live Stripe keys).

## Blocked patterns

`*.db` / `*.sqlite*`, `**/.env` / `.env.*`, `**/venv/` + `**/.venv/`,
`**/node_modules/`, `**/.DS_Store`

## Activate (once per clone)

```bash
git config core.hooksPath .githooks
```

Hooks are NOT cloned automatically — after any fresh `git clone`, run the line
above. Active on the deploy box (openclaw) as of Sep 2026.

## Behavior

- Scans only commits new to the remote (`remote_sha..local_sha`), so old
  history never triggers false blocks.
- New-branch pushes scan the full tip tree.
- Branch deletions pass through.

## Emergencies

```bash
git push --no-verify
```

If you ever need this, the artifact is probably in history for real — think
twice, and for `*.db`/`.env` assume it's a leak (Stripe keys are LIVE).

## Self-test recipe (verified working Sep 2026)

```bash
touch backend/guard-test.db && git add backend/guard-test.db && git commit -m t
git push   # -> REFUSING ... backend/guard-test.db, exit 1
git reset --hard HEAD~1
```
