.PHONY: help clean clean-pyc clean-build clean-test lint test coverage release dist docs docs-serve
SHELL := /bin/bash

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - lint code with ruff"
	@echo "test - run the test suite with pytest"
	@echo "coverage - run tests and report coverage"
	@echo "release - build and upload a release with twine"
	@echo "dist - build sdist and wheel"
	@echo "docs - build the Docusaurus documentation site"
	@echo "docs-serve - run the Docusaurus development server"

clean: clean-build clean-pyc clean-test

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

lint:
	ruff check newsworker tests

test:
	pytest -q

coverage:
	coverage run --source newsworker -m pytest
	coverage report -m
	coverage html
	python -m webbrowser htmlcov/index.html

release: dist
	twine upload dist/*

dist: clean
	python -m build
	ls -l dist

docs:
	cd docs && npm ci && npm run build

docs-serve:
	cd docs && npm start
