@echo off
rem ps-docparser Unit Tests Runner
echo Running Unit Tests and calculating coverage...
pytest tests\unit -v --cov --cov-report=term-missing
