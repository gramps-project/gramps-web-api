#!/bin/sh
set -e

# create random flask secret key
if [ ! -s /app/secret/secret ]
then
    mkdir -p /app/secret
    python3 -c "import secrets;print(secrets.token_urlsafe(32))"  | tr -d "\n" > /app/secret/secret
fi
# use the secret key if none is set (will be overridden by config file if present)
if [ -z "$GRAMPSWEB_SECRET_KEY" ]
then
    export GRAMPSWEB_SECRET_KEY=$(cat /app/secret/secret)
fi

# Create search index if not exists
if [ ! -f /app/indexdir/search_index.db ] && [ "${GRAMPSWEB_TREE}" != "*" ];
then
    python3 -m gramps_webapi --config /app/config/config.cfg search index-full
fi

# Run migrations for user database, if any
cd /app/src/
python3 -m gramps_webapi --config /app/config/config.cfg user migrate
cd /app/

exec "$@"
