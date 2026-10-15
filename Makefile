PYTHON ?= python3
.PHONY: check
check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/check_release.py
	$(PYTHON) am-code/check_publication.py
	$(PYTHON) am-code/test_base_runtime.py
	$(PYTHON) am-code/test_prompt_cli.py
	$(PYTHON) am-code/test_supplemental_corpus.py
	$(PYTHON) am-code/repack_model14b.py --self-check
	$(PYTHON) am-code/qualification.py --self-check
	$(PYTHON) am-code/final_qualification.py --self-check
	$(PYTHON) am-code/qualification_v2.py --self-check
	$(PYTHON) am-code/infer_v2_selfcheck.py
	PYTHONPATH=am-code/evaluation $(PYTHON) -m unittest test_policy_v2.ProfileBindingTests test_evaluate_v2
