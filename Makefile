.PHONY: help check-fmt fmt lint spelling test typecheck

MAKEFLAGS += --no-print-directory

UV := $(shell command -v uvx 2>/dev/null)
WITH_ACT ?= 0
ACT_TEST_ENV = $(if $(filter 1 true yes on,$(WITH_ACT)),RUN_ACT_VALIDATION=1,)
TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.1
TYPOS_CONFIG_BUILDER = $(UV) --from \
	"git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_VERSION)" \
	typos-config-builder

ifeq ($(strip $(UV)),)
$(error uvx is required to run template tests. Install uv from https://docs.astral.sh/uv/getting-started/installation/)
endif

test: ## Run template tests
	$(ACT_TEST_ENV) $(UV) --with hypothesis --with pytest-copier --with pyyaml --with syrupy --with make-parser pytest tests/

check-fmt: ## Verify template test formatting
	$(UV) ruff format --check tests/

fmt: ## Format parent tests and Markdown sources
	$(UV) ruff format tests/
	mdformat-all

lint: ## Run template test lint checks
	$(UV) ruff check tests/
	$(UV) --with interrogate interrogate --fail-under 100 tests/

spelling: ## Enforce en-GB-oxendict spelling
	$(TYPOS_CONFIG_BUILDER) gate --repository . --scope all

typecheck: ## Run template test type checks
	$(UV) --with hypothesis --with pytest --with pytest-copier --with pyyaml --with syrupy --with make-parser ty@0.0.56 check tests/

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":.*?## "; printf "Available targets:\n"} {printf "  %-15s %s\n", $$1, $$2}'
