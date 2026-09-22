all:
	@echo '## Make commands ##'
	@echo
	@$(MAKE) -pRrq -f $(lastword $(MAKEFILE_LIST)) : 2>/dev/null | awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}' | sort | egrep -v -e '^[^[:alnum:]]' -e '^$@$$' | xargs

lint:
	ruff format --check
	ruff check

format:
	ruff format
	ruff check --fix

test:
	MPLBACKEND='agg' pytest tests

test-copy-paste:
	MPLBACKEND='agg' pytest tests/labelme_tests/dlcv_tests/test_clip_paste.py tests/labelme_tests/dlcv_tests/test_clipboard_shapes.py tests/labelme_tests/dlcv_tests/test_copy_paste_gherkin.py -q

coverage-copy-paste:
	mkdir -p .qa-reports
	MPLBACKEND='agg' pytest tests/labelme_tests/dlcv_tests/test_clip_paste.py tests/labelme_tests/dlcv_tests/test_clipboard_shapes.py tests/labelme_tests/dlcv_tests/test_copy_paste_gherkin.py --cov=labelme.dlcv.utils.clip_paste --cov-report=term-missing --cov-report=json:.qa-reports/coverage-copy-paste.json --cov-fail-under=90

mutate-copy-paste:
	mkdir -p .qa-reports
	rm -f .qa-reports/copy-paste.cr.sqlite
	cosmic-ray init tools/cosmic-ray-copy-paste.toml .qa-reports/copy-paste.cr.sqlite
	cosmic-ray exec tools/cosmic-ray-copy-paste.toml .qa-reports/copy-paste.cr.sqlite
	cr-report .qa-reports/copy-paste.cr.sqlite

qa-copy-paste:
	python tools/qa_copy_paste.py

