CC ?= clang
CFLAGS ?= -O2 -Wall -Wextra -Werror
PYTHON3 ?= python3

.PHONY: all check clean

all: bin/ullage-fd-exec

bin/ullage-fd-exec: src/ullage-fd-exec.c
	$(CC) $(CFLAGS) -arch arm64 -arch x86_64 -o $@ $<

check:
	@set -eu; \
	for script in bin/ullage-bridge bin/ullage-install bin/ullage-remove bin/ullage-reap bin/ullage-cloud-hook; do \
		sh -n "$$script"; \
	done
	@$(PYTHON3) -m py_compile bin/ullage-appinfo.py
	@$(PYTHON3) -m py_compile bin/ullage-path.py
	@$(PYTHON3) bin/ullage-appinfo.py --help >/dev/null
	@$(PYTHON3) tests/test_appinfo.py
	@$(PYTHON3) tests/test_paths.py
	@$(PYTHON3) tests/test_reap.py
	@$(PYTHON3) -m py_compile bin/ullage-cloud-path.py
	@$(PYTHON3) tests/test_cloud_path.py
	@$(PYTHON3) -m py_compile bin/ullage-cloud-sync.py
	@$(PYTHON3) tests/test_cloud_sync.py
	@$(PYTHON3) -m py_compile bin/ullage-cloud-native.py
	@$(PYTHON3) tests/test_cloud_native.py
	@node --check bin/ullage-cloud-cdp.mjs

clean:
	@if test -e bin/ullage-fd-exec; then unlink bin/ullage-fd-exec; fi
	@if test -e bin/__pycache__/ullage-appinfo.cpython-*.pyc; then \
		unlink bin/__pycache__/ullage-appinfo.cpython-*.pyc; \
	fi
	@if test -e bin/__pycache__/ullage-path.cpython-*.pyc; then \
		unlink bin/__pycache__/ullage-path.cpython-*.pyc; \
	fi
	@if test -d bin/__pycache__; then rmdir bin/__pycache__; fi
