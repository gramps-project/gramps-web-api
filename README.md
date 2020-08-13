# web-api

A RESTful web API for Gramps

## Development instructions

### Install prerequisites

To start development, please install the dependencies by running
```
pip install requirements-dev.txt
```

### Set up pre-commit hooks

To set up the pre-commit hooks for the repository, run
```
pre-commit
```
in the repository root. This will make sure that all source files are nicely formatted with `black`.

### Run tests

To run the unit tests, run
```
pytest
```
in the repository root.

### Install the library in editable mode

Run
```
pip install -e . --user
```

### Run the app in development mode


Run
```
python -m gramps_webapi
