.PHONY: help test

MAKEFLAGS += --no-print-directory

test: ## Run template tests
	uvx --with pytest-copier --with pyyaml --with syrupy --with make-parser pytest tests/

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":.*?## "; printf "Available targets:\n"} {printf "  %-15s %s\n", $$1, $$2}'
