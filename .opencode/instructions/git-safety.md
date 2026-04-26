# Git Safety Rules

- Write changes directly into the current project worktree. Do not stage, commit, amend, tag, push, pull, merge, rebase, checkout, switch, reset, or clean.
- Use git only for local inspection such as `git status`, `git diff`, `git log`, and `git show`.
- Never modify content under `.git/`.
- Do not revert user changes unless the user explicitly asks for that exact revert.
- If unrelated files are already dirty, leave them alone and focus only on the requested scope.
- Prefer normal file edits in the repository over temporary patch files. Use temp space only for scratch artifacts that do not belong in the repo.
- Keep all durable changes inside the project unless the user explicitly requests a wider filesystem action.
