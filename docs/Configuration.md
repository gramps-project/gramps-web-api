# Configuration

A configuration file is necessary to run the Gramps Web API. Its path can either be provided on the command line when running the module as a script (`python3 -m gramps_webapi --config path/to/config.cfg ...`), or as an environment variable, `GRAMPS_API_CONFIG=path/to/config.cfg`.

The following settings can be specified in the configuration file.


## Required settings

Key | Description
----|------------
`TREE` | The name of the family tree database to use. Show available trees with `gramps -l`
`SECRET_KEY` | The secret key for flask. This must be set for use in production. The secret must not be shared publicly. Changing it will invalidate all access tokens.`

 You can generate a secure secret key e.g. with the command

```
python3 -c "import secrets;print(secrets.token_urlsafe(32))"
```

## Optional settings

Key | Description
----|------------
`MEDIA_BASE_DIR` | Path to use as base directory for media files, overriding the media base directory set in Gramps
`SEARCH_INDEX_DIR` | Path for the full-text search index. Defaults to `indexdir` relative to the path where the script is run
`STATIC_PATH` | Path to serve static files from (e.g. a static web frontend)
`BASE_URL` | Base URL where the API can be reached (e.g. `https://mygramps.mydomain.com/`). This is necessary e.g. to build correct passwort reset links
`CORS_ORIGINS` | Origins where CORS requests are allowed from. By default, all are disallowed. Use `"*"` to allow requests from any domain.
`EMAIL_HOST` | SMTP server host (e.g. for sending password reset e-mails)
`EMAIL_PORT` | SMTP server port
`EMAIL_HOST_USER` | SMTP server username
`EMAIL_HOST_PASSWORD` | SMTP server password
`EMAIL_USE_TLS` | Boolean, whether to use TLS for sending e-mails. Defaults to false
`DEFAULT_FROM_EMAIL` | "From" address for automated e-mails
`THUMBNAIL_CACHE_CONFIG` | Dictionary with settings for the thumbnail cache. See [Flask-Caching](https://flask-caching.readthedocs.io/en/latest/) for possible settings.


## Settings only during development

Key | Description
----|------------
`DISABLE_AUTH` | If `True`, disable the authentication system. **Warning: never** use this in a production environment, as it will allow read and write access from the public!

## Example configuration file

A minimal configuration file for production could look like this:
```python
TREE="My Family Tree"
BASE_URL="https://mytree.example.com"
SECRET_KEY="..."  # your secret key
USER_DB_URI="sqlite:////path/to/users.sqlite"
EMAIL_HOST="mail.example.com"
EMAIL_PORT=465
EMAIL_USE_TLS=True
EMAIL_HOST_USER="gramps@example.com"
EMAIL_HOST_PASSWORD="..." # your SMPT password
DEFAULT_FROM_EMAIL="gramps@example.com"
```
