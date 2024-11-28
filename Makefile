.PHONY: install test lint format clean run

run:
	poetry run streamlit run src/auto_vpn/web/streamlit_app.py

run-debug:
	poetry run streamlit run src/auto_vpn/web/streamlit_app.py --logger.level=debug
