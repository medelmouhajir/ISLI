# Contributing to ISLI

First off, thank you for considering contributing to ISLI! It's people like you that make ISLI such a great tool.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## How Can I Contribute?

### Reporting Bugs

*   **Check existing issues:** Before opening a new issue, please search the [existing issues](https://github.com/medelmouhajir/ISLI/issues) to see if it has already been reported.
*   **Use the template:** Use the Bug Report template when opening a new issue.
*   **Be specific:** Include as much detail as possible: your operating system, version of ISLI, steps to reproduce, and any relevant logs or screenshots.

### Suggesting Enhancements

*   **Check existing issues:** See if your idea has already been suggested.
*   **Use the template:** Use the Feature Request template.
*   **Explain the "Why":** Describe the problem you're trying to solve and how the enhancement would help.

### Pull Requests

1.  **Fork the repo** and create your branch from `main`.
2.  **Install dependencies:** Follow the setup instructions below.
3.  **Make your changes:** Ensure your code follows the project's style.
4.  **Add tests:** If you're adding a feature or fixing a bug, please include tests.
5.  **Run tests:** Ensure all tests pass.
6.  **Submit the PR:** Provide a clear description of your changes and link to any relevant issues.

---

## Local Development Setup

### 1. Architectural Integrity
*   **Shared Blackboard**: Agents MUST NOT communicate directly. All delegation MUST happen via creating a Task on the Kanban board.
*   **Keeper First**: Use the Keeper for summarization and context injection to minimize latency and token costs.

### 2. Implementation Guardrails
*   **Asynchronous Patterns**: Use `async`/`await` for all I/O bound operations.
*   **Structured Logging**: Use `structlog` for all Python services.
*   **Python Typing**: Strict typing is required. Use `mypy` for verification.
*   **Linting**: Use `ruff` for linting and formatting.

### 3. Development Environment

#### Management CLI (Recommended)
The easiest way to set up and manage your development environment is using the `isli` CLI.

```bash
# Guided setup
./isli setup

# Start the stack
./isli up
```

#### Docker (Manual)
```bash
# Setup environment
cp .env.example .env
# Edit .env with your secrets

# Start all services
docker compose up --build
```

#### Native Development

**Backend (isli-core)**
```bash
cd isli-core
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn isli_core.main:app --reload --port 8000
```

**Frontend (isli-board)**
```bash
cd isli-board
npm install
npm run dev
```

### 4. Running Tests
Each service uses `pytest`. Run core tests with:
```bash
cd isli-core
pytest
```

---

## Style Guide

### Python
*   Follow PEP 8.
*   Use `ruff` for formatting.
*   Use type hints for all function signatures.

### TypeScript / React
*   Use functional components with hooks.
*   Strict typing for all API payloads and WebSocket events.
*   Follow existing Tailwind CSS patterns for styling.

## Questions?
If you have any questions, feel free to open an issue or reach out to Mohamed Amin ELMOUHAJIR at **itp.coder@gmail.com**.
