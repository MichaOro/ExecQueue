# MCP Usage Rules

- Prefer native OpenCode read, edit, grep, and bash tools for normal repository work. Use MCP when it clearly adds leverage.
- Use `sequential-thinking` for multi-step decomposition, debugging plans, and architecture tradeoff analysis.
- The filesystem MCP is available for project-adjacent inspection and temp-space work. Prefer native project file tools for files already inside the repo.
- The git MCP is configured but intentionally denied through permissions in this project because shell-level read-only git inspection is enough and mutating git flows are not allowed here.
- The postgres MCP is denied globally for normal agents. Only `db-inspector` may use it for read-oriented inspection, and only `db-writer` may use it for explicit database changes.
- Treat the configured Postgres connection as potentially privileged. Unless a read-only role is introduced, default normal usage to schema discovery and read-only inspection.
- State-changing SQL is reserved for the `db-writer` agent and should only happen after an approval prompt.
- Temp directories are acceptable for ephemeral inspection or generated scratch output. Other external directories should stay exceptional and justified.
