#!/bin/bash

# Dev Container startup script
set -e

# Install dependencies
pip install -r requirements-dev.txt
pip install -e .[ai]

# Copy Gramps addons from build location to runtime location
mkdir -p /workspaces/web-api/data/gramps/gramps60/plugins
if [ -d /home/vscode/gramps/gramps60/plugins ] && [ "$(ls -A /home/vscode/gramps/gramps60/plugins)" ]; then
    echo "Copying Gramps addons to runtime location..."
    cp -rn /home/vscode/gramps/gramps60/plugins/* /workspaces/web-api/data/gramps/gramps60/plugins/
fi

mkdir -p /workspaces/web-api/data/grampsdb
# Check if the grampsdb directory is empty
if [ -z "$(ls -A /workspaces/web-api/data/grampsdb)" ]; then
    echo "Database directory is empty, initializing..."
    # Create necessary directories if they don't exist
    mkdir -p /workspaces/web-api/data/grampsdb
    gramps -C Gramps\ Web -i  /usr/local/share/doc/gramps/example/gramps/example.gramps --config=database.backend:sqlite --config=database.path:/workspaces/web-api/data/grampsdb
    mkdir -p /workspaces/web-api/data/media
    cp -a /usr/local/share/doc/gramps/example/gramps/. /workspaces/web-api/data/media/

    python3 -m gramps_webapi user add owner owner --fullname Owner --role 4 \
    && python3 -m gramps_webapi user add editor editor --fullname Editor --role 3 \
    && python3 -m gramps_webapi user add contributor contributor --fullname Contributor --role 2 \
    && python3 -m gramps_webapi user add member member --fullname Member --role 1
else
    echo "Database directory already contains data, skipping initialization"
fi
