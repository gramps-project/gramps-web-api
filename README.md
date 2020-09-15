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

### Generate a configuration file

Example content:

```python
TREE="My Family Tree"
```

### Run the app in development mode


Run
```
python -m gramps_webapi --config path/to/config run
```
The API will be accesible at `http://127.0.0.1:5000` by default. To choose a different port, add the `--port` option.
