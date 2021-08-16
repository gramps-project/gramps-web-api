### Python version

The web API only works with Python 3.6 or newer.

### Install Gramps

The web API requires the Gramps Python library to be importable. Starting from Gramps 5.2.0, it will be installable via `pip`. For the time being, the two most convenient options are

1. Use the `apt` package `python3-gramps` on Ubuntu
2. Build your own wheel from Gramps `master` and install it into a virtual environment. Instructions:

```
python3 -m venv gramps_webapi
source gramps_webapi/bin/activate
python3 -m pip install wheel
git clone https://github.com/gramps-project/gramps.git
cd gramps
python3 setup.py bdist_wheel
python3 -m pip install dist/*.whl
```
**Warning:** Gramps `master` is an unstable development snapshot. Do not use it on your existing family tree.

### Install prerequisites

To start development, please install the dependencies by running
```
pip install requirements-dev.txt
```

### Set up pre-commit hooks

To set up the pre-commit hooks for the repository, run
```
pre-commit install
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
DISABLE_AUTH=True
```

### Run the app in development mode


Run
```
python -m gramps_webapi --config path/to/config run
```
The API will be accesible at `http://127.0.0.1:5000` by default. To choose a different port, add the `--port` option.
