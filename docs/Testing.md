# Testing the API locally

On Linux, you can try out the Gramps Web API locally with your existing family tree by installing and running the Python application. The following assumes that your Python 3 executabe is called `python3`.

## Install

First, make sure you have installed Gramps and can import the Python package. Running
```
python3 -c 'import gramps'
```
on the command line should not return an error.

Then, install the `gramps-webapi` Python package as

```
python3 -m pip install --user gramps-webapi
```

## Configure

Before running the application, we need to create a minimal configuration file.

!!! warning
    Do not use this configuration in production.

Create a file `test.cfg` with the content
```
TREE="My Family Tree"
DISABLE_AUTH=True
```
replacing `My Family Tree` with the name of your family tree database. Use `gramps -l` to list admissible names.

## Run

!!! warning
    Please back up your family tree before starting to test the Web API on your research data.

!!! note
    When running the Python application directly, please close Gramps desktop before starting the API, even though modifying the database will fail as it is locked (so the database cannot be corrupted).


Now, you can run the Web API with the command

```
python3 -O -m gramps_webapi --config test.cfg run --port 5555
```

You can now start interacting with the API at `http://localhost:5555/api`.

!!! warning
    Do not expose this as-is to a public network or the internet, as anyone will be able to view and modify your family tree!
