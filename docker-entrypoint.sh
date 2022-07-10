#!/bin/sh
set -e

# Use Gramps.js frontend
if [ -n "$GRAMPSJS_VERSION" ]
then
    # Download if necessary
    if ! [ -d "/app/static/grampsjs-${GRAMPSJS_VERSION}" ]
    then
        wget "https://github.com/DavidMStraub/Gramps.js/releases/download/${GRAMPSJS_VERSION}/grampsjs-${GRAMPSJS_VERSION}.tar.gz"
        tar -xzf "grampsjs-${GRAMPSJS_VERSION}.tar.gz"
        mv "grampsjs-${GRAMPSJS_VERSION}" static/
    fi
    export STATIC_PATH="/app/static/grampsjs-${GRAMPSJS_VERSION}"
fi

# create random flask secret key
if [ ! -s /app/secret/secret ]
then
    mkdir -p /app/secret
    python3 -c "import secrets;print(secrets.token_urlsafe(32))"  | tr -d "\n" > /app/secret/secret
fi
# use the secret key if none is set (will be overridden by config file if present)
if [ -z "$SECRET_KEY" ]
then
    export SECRET_KEY=$(cat /app/secret/secret)
fi

# Create search index if not exists
if [ -z "$(ls -A /app/indexdir)" ]
then
    python3 -m gramps_webapi --config /app/config/config.cfg search index-full
fi

# Run migrations for user database, if any
cd /app/src/
GRAMPS_API_CONFIG=/app/config/config.cfg python3 -m alembic upgrade head
cd /app/

exec "$@"
