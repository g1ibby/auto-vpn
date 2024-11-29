.PHONY: install test lint format clean run run-debug docker-build docker-run docker-run-debug

# Change this command
run:
	streamlit run auto_vpn/web/streamlit_app.py

run-debug:
	streamlit run auto_vpn/web/streamlit_app.py --logger.level=debug

# Docker commands
docker-build:
	docker build -t auto-vpn .

docker-run:
	docker run -p 8501:8501 \
		--name auto-vpn \
		-v $(PWD)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro \
		-v $(HOME)/.ssh:/home/appuser/.ssh:ro \
		auto-vpn

docker-run-debug:
	docker run -p 8501:8501 \
		--name auto-vpn \
		auto-vpn run-debug

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
