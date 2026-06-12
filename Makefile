appname = aa-sov-monitor
package = aa_sov_monitor

# Languages shipped with this app (English is the source language).
languages = de

# Default goal
.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo ""
	@echo "$(appname) Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make [command]"
	@echo ""
	@echo "Commands:"
	@echo "  test                    Run the test suite"
	@echo "  coverage                Run tests and create a coverage report"
	@echo "  tox_tests               Run tests with tox across Python versions"
	@echo "  pre-commit-checks       Run pre-commit on all files"
	@echo "  translations            Create or update translation (.po) files"
	@echo "  compile_translations    Compile translation (.mo) files"
	@echo "  build_test              Build the package"
	@echo ""

# Run tests (standalone via the bundled testauth project)
.PHONY: test
test:
	@DJANGO_SETTINGS_MODULE=testauth.settings.local python runtests.py $(package) -v 2

# Coverage
.PHONY: coverage
coverage:
	@rm -rf htmlcov
	@coverage run runtests.py $(package) -v 2
	@coverage html
	@coverage report -m

# Tox tests
.PHONY: tox_tests
tox_tests:
	@tox

# Pre-commit checks
.PHONY: pre-commit-checks
pre-commit-checks:
	@pre-commit run --all-files

# Translation files (run from inside the package directory)
.PHONY: translations
translations:
	@cd $(package) && django-admin makemessages \
		$(foreach lang,$(languages),-l $(lang)) \
		--keep-pot \
		--ignore 'build/*'

# Compile translation files
.PHONY: compile_translations
compile_translations:
	@cd $(package) && django-admin compilemessages \
		$(foreach lang,$(languages),-l $(lang))

# Build package
.PHONY: build_test
build_test:
	@rm -rf dist
	@python3 -m build
