# Codex instructions

This project uses Conda.

The existing Conda environment name is: lingmate.

## Command execution rules

Always run Python-related commands through the `lingmate` Conda environment.

Use these command forms:

    conda run -n lingmate python
    conda run -n lingmate pip
    conda run -n lingmate pytest
    conda run -n lingmate python -m pytest

Do not use these bare commands:

    python
    py
    pip
    pytest
    python -m pytest

## Examples

Run a Python script:

    conda run -n lingmate python path/to/script.py

Run tests:

    conda run -n lingmate pytest

Install packages:

    conda run -n lingmate pip install <package>

Check the active Python executable:

    conda run -n lingmate python -c "import sys; print(sys.executable)"

Check installed packages:

    conda run -n lingmate pip list

## Notes for Codex

Before diagnosing Python errors, first confirm that commands are running inside the `lingmate` Conda environment.

When reproducing bugs, running tests, installing packages, or executing scripts, always use `conda run -n lingmate`.

Prefer modifying project files only after reproducing the issue using the `lingmate` environment.