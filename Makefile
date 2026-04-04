PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

EXT_NAME = talib
EXT_CONFIG = ${PROJ_DIR}extension/extension_config.cmake
DUCKDB_SRCDIR = ${PROJ_DIR}duckdb/

# Allow SQL tests on macOS / local Linux (CI docker sets this to 1 by default in upstream makefile)
LINUX_CI_IN_DOCKER ?= 1

include extension-ci-tools/makefiles/duckdb_extension.Makefile
