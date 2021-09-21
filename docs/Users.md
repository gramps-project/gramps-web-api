# User system

The Gramps Web API comes with an authentication system with role-based user permissions.

## User roles

The following user roles are currently defined.

Role | Role ID | Permissions
-----|---------|------------
Guest | 0 | View non-private objects
Member | 1 | Guest + view private objects
Contributor | 2 | Member + add objects
Editor | 3 | Contributor + edit and delete objects
Owner | 4 | All: Editor + manage users

## Managing users

There are two ways to manage users:

- With owner permissions using the API (needs a running server secured with SSL/TLS): see [API docs](api.md)
- On the command line on the server running the API.

### Managing users on the command line

The basic command is

```bash
python3 -m gramps_webapi --config path/to/config.cfg user COMMAND [ARGS]
```
or, when using a [Docker deployment](Deployment.md),

```bash
docker-compose run gramps_webapi \
    python3 -m gramps_webapi user COMMAND [ARGS]
```

The `COMMAND` can be `add` or `delete`. Use `--help` for `[ARGS]` to show the syntax and possible configuration options.
