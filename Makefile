.PHONY: check
check:
	python3 -m unittest discover -s tests -v
	python3 scripts/check_release.py
