# Repository agent guidelines

These instructions apply to all work in this repository.

## Issue workflow

1. Inspect the issue, repository documentation, and current Git status before
   editing. Preserve unrelated local changes.
2. Work on each issue in a **new, dedicated branch** based on the latest
   `origin/main`. Fetch first and use a descriptive name such as
   `<issue-number>-<short-description>` or `docs/<short-description>` when no
   issue number exists. Do not make issue changes directly on `main` or reuse
   another issue's branch.
3. Implement the issue with focused changes consistent with the surrounding
   code. Add or update meaningful tests when behavior changes.
4. Execute tests for every PR, including documentation-only PRs, and review
   documentation as described below. Resolve regressions before completion;
   report any pre-existing failures or environment blockers explicitly.
5. Review the full diff and commit **all issue-related changes** to the dedicated
   branch, including tests and documentation. Keep unrelated files, generated
   artifacts, and secrets out of the commits. Follow the existing concise commit
   style, for example `docs: add repository agent guidelines`.
6. Push all issue commits to that branch on `origin` (set upstream on the first
   push: `git push -u origin <branch>`).
7. Open a pull request against `main` with `gh pr create`. Describe the changes,
   link the issue (`Closes #<number>` when appropriate), and record the exact
   verification commands and results, including skipped checks and blockers.
   Include the documentation review outcome. For any PR involving UI changes,
   include screenshots in the PR description or a PR comment that document the
   changed interface for review. Use before-and-after screenshots when updating
   an existing interface, and label the relevant screens and states.
8. Add a **PR comment summarizing the completed changes**, test results, and
   documentation updates or why none were needed, using `gh pr comment`.
   Return the PR URL to the user. Follow-up changes belong on the same issue
   branch; commit, test, and push them, and update the PR summary as needed.

## Repository map

- `src/provider_simenv/`: Python simulation engine, HTTP APIs, database storage,
  and export tooling.
- `tests/`: Python regression and integration tests.
- `web/`: React/TypeScript globe frontend, with its own npm scripts and tests.
- `docs/`: API, database, playback, and other detailed guides.
- `README.md` and `web/README.md`: installation, usage, and frontend workflows.
- `pyproject.toml` and `tox.ini`: Python dependencies and verification commands.

## Verification required for every PR

Run commands from the repository root unless otherwise stated.

Install the Python development dependencies in a virtual environment:

```bash
pip install -e '.[dev]'
```

Run the Python regression suite for every PR, even for documentation-only work:

```bash
python -m pytest tests
```

For Python changes, also run the configured lint and type checks. The full tox
suite runs lint, type checking, and tests:

```bash
python -m tox
```

For frontend changes, run from `web/`:

```bash
npm ci
npm run typecheck
npm run lint
npm run build
```

Also execute the relevant frontend tests from `web/package.json`, such as
`npm run test:simulation` or `npm run test:playback`. Consult `web/README.md` and
`docs/playback.md` for the API, PostgreSQL, browser, and other prerequisites
needed by integration, browser, and performance tests. Run relevant integration
checks when changing API, database, simulation, or playback behavior.

Inspect test output for skips as well as failures. Record unavailable services
or dependencies and unexecuted checks in the PR; do not describe skipped or
blocked checks as passing. After fixes, rerun affected checks before pushing.

## Documentation review required for every PR

Check `README.md`, `web/README.md`, and the relevant files in `docs/` against the
changes. Update documentation in the same branch whenever behavior, setup,
configuration, interfaces, schemas, or contributor workflows change. Verify
documented commands, paths, and links against the repository. If no revision is
needed, explicitly record that conclusion and its reason in the PR and summary
comment.

## Change conventions

- Keep changes scoped to the issue and follow existing Python and TypeScript
  patterns. Ruff's configured Python line length is 78 characters.
- Edit `SimulatorScenarios_template.csv` for scenario defaults rather than the
  generated working `SimulatorScenarios.csv`.
- Keep PDL scenarios and their matching roster sidecars consistent.
- Before committing, inspect `git status`, `git diff`, and recent commit history;
  stage only intended files. Before opening the PR, review all commits and the
  complete diff against `origin/main`.
