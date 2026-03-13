.PHONY: lint format-check hassfest check fix

# Run ruff linter (mirrors lkempf CI)
lint:
	python3 -m ruff check .

# Check formatting without modifying (mirrors lkempf DEVELOPMENT.md)
format-check:
	python3 -m black . --check

# Run hassfest validation via Docker (mirrors lkempf CI)
hassfest:
	docker run --rm \
	  -v $(shell pwd)/custom_components:/github/workspace/custom_components \
	  ghcr.io/home-assistant/hassfest:latest

# Run all checks in sequence — must pass before any PR to lkempf
check: lint format-check hassfest

# Auto-fix lint and formatting issues
fix:
	python3 -m ruff check . --fix
	python3 -m black .
