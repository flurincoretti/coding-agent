default:
    just --list --unsorted

install:
    uv venv
    uv sync

run:
    uv run agent

lint:
    uv run ruff check --extend-select I

format:
    uv run ruff format

fix:
    uv run ruff check --extend-select I --fix
    uv run ruff format

clean:
    rm -rf .ruff_cache
    rm -rf .pytest_cache
    fd -I __pycache__ --type d --prune -x rm -r
