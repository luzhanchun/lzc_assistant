# Codex instructions

This project uses Conda.

The existing Conda environment name is: cook.

## Command execution rules

Always run Python-related commands through the `cook` Conda environment.

Use these command forms:

    conda run -n cook python
    conda run -n cook pip
    conda run -n cook pytest
    conda run -n cook python -m pytest

Do not use these bare commands:

    python
    py
    pip
    pytest
    python -m pytest

## Examples

Run a Python script:

    conda run -n cook python path/to/script.py

Run tests:

    conda run -n cook pytest

Install packages:

    conda run -n cook pip install <package>

Check the active Python executable:

    conda run -n cook python -c "import sys; print(sys.executable)"

Check installed packages:

    conda run -n cook pip list

## Notes for Codex

Before diagnosing Python errors, first confirm that commands are running inside the `cook` Conda environment.

When reproducing bugs, running tests, installing packages, or executing scripts, always use `conda run -n cook`.

Prefer modifying project files only after reproducing the issue using the `cook` environment.