#!/bin/bash
set -e

python3 -m gramps_webapi --config /app/config/config.cfg search index-full

exec "$@"
