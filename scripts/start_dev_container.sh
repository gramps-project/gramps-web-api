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
    python3 scripts/init_dev_trees.py
else
    echo "Database directory already contains data, skipping initialization"
fi
