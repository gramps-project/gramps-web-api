# Gramps Web API

This is the repository for **Gramps Web API**, a Python REST API for [Gramps](https://gramps-project.org).

It allows to query and manipulate a [Gramps](https://gramps-project.org) family tree database via the web.

Gramps Web API is the backend of [Gramps Web](https://www.grampsweb.org/), a genealogy web app based on Gramps, but can also be used as backend for other tools.

## More information

- API documentation for Gramps Web API: https://gramps-project.github.io/gramps-web-api/
- Developer documentation for Gramps Web API: https://www.grampsweb.org/development/backend/
- Documentation for Gramps Web: https://www.grampsweb.org

## Related projects

- Gramps Web frontend repository: https://github.com/gramps-project/gramps-web

## Security & Docker Migration
Following a security hardening process, the Gramps Web API container now runs as an unprivileged non-root user (`gramps`, UID 1000).
If you are upgrading an existing installation using Docker Compose and have mounted host directories, you must change their ownership before starting the new container to avert permission errors:
```bash
sudo chown -R 1000:1000 /path/to/your/mounted/volumes
```
