.PHONY: install test lint format clean run run-debug docker-build docker-run

run:
	streamlit run src/auto_vpn/web/web.py

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
