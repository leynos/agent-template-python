.PHONY: help test

MAKEFLAGS += --no-print-directory

UV := $(shell command -v uvx 2>/dev/null)

ifeq ($(strip $(UV)),)
$(error uvx is required to run template tests. Install uv from https://docs.astral.sh/uv/getting-started/installation/)
endif

test: ## Run template tests
	$(UV) --with pytest-copier --with pyyaml --with syrupy --with make-parser pytest tests/

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":.*?## "; printf "Available targets:\n"} {printf "  %-15s %s\n", $$1, $$2}'
