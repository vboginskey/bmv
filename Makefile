all: run

run:
	. .venv/bin/activate \
	&& export $$(cat .env | xargs) \
	&& python main.py 2>&1 | tee run.log

.PHONY: run
