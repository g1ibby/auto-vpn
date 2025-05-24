.PHONY: setup venv install install-dev test lint format clean run run-debug docker-build docker-run docker-stop docker-logs docker-shell docker-clean bump-patch bump-minor bump-major bump-push update-plugins

VENV := .venv

venv:
	uv venv $(VENV)

setup: venv
	uv pip install -U pip

install: setup
	uv pip install -e .

install-dev: setup
	uv pip install -e ".[dev]"

run: install
	. $(VENV)/bin/activate && streamlit run src/auto_vpn/web/web.py

test: install-dev
	. $(VENV)/bin/activate && pytest

lint: install-dev
	. $(VENV)/bin/activate && ruff check src tests
	. $(VENV)/bin/activate && ruff format --check src tests
	. $(VENV)/bin/activate && mypy src tests

format: install-dev
	. $(VENV)/bin/activate && ruff format src tests
	. $(VENV)/bin/activate && ruff check --fix src tests

clean:
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker build -t auto-vpn .

docker-run:
	docker run -p 8501:8501 \
		--name auto-vpn \
		auto-vpn

docker-stop:
	docker stop auto-vpn && docker rm auto-vpn

docker-logs:
	docker logs -f auto-vpn

docker-shell:
	docker exec -it auto-vpn /bin/bash

# Clean up
docker-clean:
	docker stop auto-vpn || true
	docker rm auto-vpn || true
	docker rmi auto-vpn || true

# Version bumping
bump-patch: install-dev
	bump-my-version bump patch

bump-minor: install-dev
	bump-my-version bump minor

bump-major: install-dev
	bump-my-version bump major

bump-push:
	git push origin main --tags

# Update Pulumi plugins
update-plugins:
	python3 update_pulumi_plugins.py
