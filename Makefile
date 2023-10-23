all: run

run:
	. .venv/bin/activate \
	&& export $$(cat .env | xargs) \
	&& python main.py

.PHONY: run