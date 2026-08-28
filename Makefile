CC ?= clang
CFLAGS ?= -O2 -Wall -Wextra -Werror
PYTHON3 ?= python3

.PHONY: all check integration clean native-probe native-session-probe native-session

all: bin/ullage-fd-exec bin/ullage-native-steam-session.dylib

native-probe: bin/ullage-native-steamclient-probe

native-session-probe: bin/ullage-native-steamclient-session-probe

native-session: bin/ullage-native-steam-session.dylib

bin/ullage-fd-exec: src/ullage-fd-exec.c
	$(CC) $(CFLAGS) -arch arm64 -arch x86_64 -o $@ $<

bin/ullage-native-steamclient-probe: tools/ullage-native-steamclient-probe.c
	$(CC) $(CFLAGS) -arch arm64 -arch x86_64 -o $@ $<

bin/ullage-native-steamclient-session-probe: tools/ullage-native-steamclient-session-probe.c
	$(CC) $(CFLAGS) -arch arm64 -arch x86_64 -o $@ $<

bin/ullage-native-steam-session.dylib: tools/ullage-native-steam-session.c
	$(CC) $(CFLAGS) -fPIC -dynamiclib -arch arm64 -arch x86_64 -o $@ $<

check:
	@set -eu; \
	for script in bin/ullagectl bin/ullage-bridge bin/ullage-install bin/ullage-remove bin/ullage-reap; do \
		sh -n "$$script"; \
	done
	@sh tests/test_install_options.sh
	@$(PYTHON3) -m py_compile bin/*.py bin/ullage tests/*.py
	@bin/ullagectl --help >/dev/null
	@$(PYTHON3) bin/ullage-appinfo.py --help >/dev/null
	@$(PYTHON3) bin/ullage-mapping.py --help >/dev/null
	@$(PYTHON3) tests/test_appinfo.py
	@$(PYTHON3) tests/test_cli.py
	@$(PYTHON3) tests/test_runtime.py
	@$(PYTHON3) tests/test_host_runtime.py
	@$(PYTHON3) tests/test_steam_client.py
	@$(PYTHON3) tests/test_mapping.py
	@$(PYTHON3) tests/test_metadata.py
	@$(PYTHON3) tests/test_paths.py
	@$(PYTHON3) tests/test_reap.py
	@$(PYTHON3) tests/test_cloud_path.py
	@$(PYTHON3) tests/test_cloud_native.py
	@sh tests/test_bridge.sh
	@sh tests/test_steamworks_probe.sh

integration: all
	@$(PYTHON3) tests/test_install_transaction.py

clean:
	@if test -e bin/ullage-fd-exec; then unlink bin/ullage-fd-exec; fi
	@if test -e bin/ullage-native-steamclient-probe; then unlink bin/ullage-native-steamclient-probe; fi
	@if test -e bin/ullage-native-steamclient-session-probe; then unlink bin/ullage-native-steamclient-session-probe; fi
	@if test -e bin/ullage-native-steam-session.dylib; then unlink bin/ullage-native-steam-session.dylib; fi
	@find bin/__pycache__ tests/__pycache__ -type f -name '*.pyc' -delete 2>/dev/null || true
	@rmdir bin/__pycache__ tests/__pycache__ 2>/dev/null || true
