#!/bin/sh
set -e

# use the secret key if none is set (will be overridden by config file if present)
if [ -z "$GRAMPSWEB_SECRET_KEY" ]
then
    # create random flask secret key
    if [ ! -s /app/secret/secret ]
    then
        mkdir -p /app/secret
        python3 -c "import secrets;print(secrets.token_urlsafe(32))"  | tr -d "\n" > /app/secret/secret
    fi
    export GRAMPSWEB_SECRET_KEY=$(cat /app/secret/secret)
fi

# Run migrations for user database, if any
cd /app/src/
python3 -m gramps_webapi --config /app/config/config.cfg user migrate
cd /app/

exec "$@"
