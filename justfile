default:
    @just --list

install:
    @uv sync --all-extras

lint:
    @uv run ruff check src tests
    @uv run ruff format --check src tests
    @uv run flake8 src tests

typecheck:
    @uv run mypy

test:
    @TERM=dumb uv run python -m pytest --doctest-modules -p no:faulthandler --no-header

build:
    @rm -rf dist
    @uv build
