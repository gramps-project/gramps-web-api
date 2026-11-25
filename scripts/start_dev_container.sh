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
# Set up the dev trees and users. Safe to rerun: it finishes an interrupted
# setup, migrates the old single-tree setup and leaves everything else alone.
python3 scripts/init_dev_trees.py
