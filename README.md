# Coding Agent

An extensible command‑line REPL based on Claude models that can call local Python "tools" to inspect and modify your project.

## Quick start

Clone and enter the repo:

```bash
git clone https://github.com/flurincoretti/coding-agent
cd coding‑agent
```

Create a virtualenv (uses `uv`):

```
uv venv
```

Install dependencies:

```
uv sync
```

Configure the environment and add your Anthropic API key:

```
cp .env.example .env
$EDITOR .env
```

Start the chat:

```
uv run agent
```
