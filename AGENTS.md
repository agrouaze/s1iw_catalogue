# s1iw_catalogue Agent Instructions

## Key Commands
- **Installation**: `make install` (installs dev dependencies and stub types)
- **Pre-commit hooks**: `make pre-commit-install`
- **Linting**: `make lint` (runs tests, codestyle checks, type checks, and security checks)
- **Codestyle**: `make codestyle` (formats code with `pyupgrade`, `isort`, and `black`)
- **Type checks**: `make mypy`
- **Tests**: `make test` (runs pytest with coverage and generates a badge)
- **Security checks**: `make check-safety` (runs `pip check`, `safety`, and `bandit`)

## Project Structure
- **Core logic**: `s1iw_catalogue/` (e.g., `catalogue.py`, `cli.py`, `backup.py`)
- **Tests**: `tests/` (e.g., `test_catalogue.py`, `test_cli.py`)
- **End-to-end tests**: `end2end/` (e.g., `check_update_workflow.py`)
- **Configuration**: `s1iw_catalogue/config.yml`

## Development Conventions
- **Python version**: 3.11+
- **Code style**: `black`, `isort`, `pyupgrade`
- **Type checks**: `mypy` (strict mode)
- **Testing**: `pytest` with coverage
- **Security**: `bandit`, `safety`
- **Dependencies**: Managed via `pyproject.toml` and `Makefile`

## Build and Release
- **Build**: Uses `hatchling` and `hatch-vcs` for versioning
- **Release**: Follows semantic versioning (see `Makefile` and `pyproject.toml`)

## Testing
- **Run tests**: `make test` (includes coverage and badge generation)
- **Check codestyle**: `make check-codestyle`
- **Lint**: `make lint` (comprehensive check)

## CI/CD
- **Workflow**: Defined in `.github/workflows/ci.yml` and `.github/workflows/cd.yml`
- **Dependencies**: Updated via Dependabot
- **Stale issues**: Managed via Stale bot

## Docker
- **Build**: `make docker-build`
- **Remove**: `make docker-remove`

## Key Files
- **Entry point**: `s1iw_catalogue/cli.py`
- **Core logic**: `s1iw_catalogue/catalogue.py`
- **Configuration**: `s1iw_catalogue/config.yml`

## Notes
- **Private dependency**: `s1ifr` is fetched from Ifremer's private PyPI index (configured in `pyproject.toml`).