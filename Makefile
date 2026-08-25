CC ?= clang
CFLAGS ?= -O2 -Wall -Wextra -Werror
PYTHON3 ?= python3

.PHONY: all check clean

all: bin/ullage-fd-exec

bin/ullage-fd-exec: src/ullage-fd-exec.c
	$(CC) $(CFLAGS) -arch arm64 -arch x86_64 -o $@ $<

check:
	@set -eu; \
	for script in bin/ullage-bridge bin/ullage-install bin/ullage-remove bin/ullage-reap; do \
		sh -n "$$script"; \
	done
	@sh tests/test_install_options.sh
	@$(PYTHON3) -m py_compile bin/*.py
	@$(PYTHON3) bin/ullage-appinfo.py --help >/dev/null
	@$(PYTHON3) bin/ullage-mapping.py --help >/dev/null
	@$(PYTHON3) tests/test_appinfo.py
	@$(PYTHON3) tests/test_mapping.py
	@$(PYTHON3) tests/test_paths.py
	@$(PYTHON3) tests/test_reap.py
	@$(PYTHON3) tests/test_cloud_path.py
	@$(PYTHON3) tests/test_cloud_native.py
	@sh tests/test_bridge.sh
	@sh tests/test_steamworks_probe.sh

clean:
	@if test -e bin/ullage-fd-exec; then unlink bin/ullage-fd-exec; fi
	@if test -d bin/__pycache__; then \
		find bin/__pycache__ -type f -name '*.pyc' -delete; \
		rmdir bin/__pycache__ 2>/dev/null || true; \
	fi
