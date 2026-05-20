# Workspace Guide

## Paths

- Workspace: `{{workspace}}`
- Skills: `{{skills_path}}`
- Crons: `{{crons_path}}`
- Memories: `{{memories_path}}`
- Agents: `{{agents_path}}`

## Directory Structure

```text
{{workspace}}
|-- config.user.yaml      # User configuration
|-- config.runtime.yaml   # Runtime state, optional and auto-managed
|-- agents/               # Agent definitions
|   |-- cyberclaw/
|   |   |-- AGENT.md
|   |   `-- SOUL.md
|   `-- vault/
|       |-- AGENT.md
|       `-- SOUL.md
|-- skills/               # Reusable skills
|-- crons/                # Scheduled tasks
`-- memories/             # Persistent memory storage
    |-- topics/
    |-- projects/
    `-- daily-notes/
```

## File Purposes

- `AGENT.md`: agent configuration and operational instructions.
- `SOUL.md`: agent personality, appended to `AGENT.md` at runtime.
- `config.user.yaml`: user preferences, API keys, and model selection.
- `config.runtime.yaml`: internal runtime state.
- `SKILL.md`: reusable skill instructions and scripts.
