default:
    @just --list

install:
    @uv sync --extra cli

lint:
    @uv run ruff check src tests
    @uv run ruff format --check src tests
    @uv run flake8 src tests

typecheck:
    @uv run mypy

test *paths:
    @TERM=dumb uv run python -m pytest -p no:faulthandler --no-header {{paths}}

build:
    @rm -rf dist
    @uv build
