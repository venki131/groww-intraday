## Git Workflow

**Branch protection rules — NEVER violate these:**
- `main` is locked. Direct pushes to `main` are forbidden.
- For every task, create a new feature branch: `git checkout -b <type>/<short-description>` (e.g. `feat/ema-strategy`, `fix/chunking-bug`, `docs/memento-init`).
- All work happens on the feature branch. Commit freely there.
- When the task is complete, push the branch and open a Pull Request against `main`:
  ```bash
  git push origin <branch-name>
  gh pr create --base main --head <branch-name> --title "<title>" --body "<description>"
  ```
- PRs must be **reviewed and approved manually** before merging. Never auto-merge or force-push to `main`.
- Branch naming convention: `<type>/<kebab-description>` where type is one of: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
