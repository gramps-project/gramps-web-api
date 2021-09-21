# Deploying with Docker

To deploy your family tree with the Gramps Web API to a server, either on your local network or the internet, the most convenient option is to use Docker. We recommand using Docker Compose and will assume that Docker and Docker Compose are already installed in your system. Your can use Windows, Mac OS, or Linux as a host system. The supported architectures include not only x86-64 (desktop systems), but also ARM systems such as a Raspberry Pi, which can serve as a low-cost, but powerful (enough) web server.

!!! note
    You do not need to install Gramps on the server as it is contained in the docker image.

## Step 1: Upload Gramps database

Upload the Gramps database from your computer to the server. This is the directory that shows up before the family tree name when you run `gramps -l`. We will assume you will put it into the directory `~/gramps_db`.

!!! note
    This only works if you use Gramps 5.1 locally and the family tree uses SQLite (BSDDB is not supported).

Alternatively, you can upload a Gramps XML export to the server and import it later.

## Step 2: Upload media files

Upload your media files to the server. Make sure your Gramps database uses relative paths and not absolute paths as these will not work. We will assume the media base directory on your server will be located at `~/gramps_media`.


!!! note
    Use the "Convert media paths from absolute to relative" option in the "Media Manager" tool in Gramps' "Tools" menu if necessary.



## Step 3: Create a configuration file

Create a configuration and upload it to your server (we will assume the path is `~/config.cfg`). It should contain at least the following lines:

```python
TREE="..."  # set the name of your family tree
SECRET_KEY="..." # set your secret key
# do not change the following lines as they refer to paths within the container
USER_DB_URI="sqlite:////app/users/users.sqlite"
MEDIA_BASE_DIR="/app/media"
SEARCH_INDEX_DIR="/app/indexdir"
STATIC_PATH="/app/static"
```

For other configuration options, see [Configuration](Configuration)

## Step 3: Docker configuration

Create a new file on the server named `docker-compose.yml` and insert the following contents:

```yaml
version: "3.7"

services:
  gramps_webapi:
    image: dmstraub/gramps-webapi:latest
    restart: always
    ports:
      - "80:5000"
    volumes:
      - gramps_users:/app/users
      - gramps_index:/app/indexdir
      - gramps_thumb_cache:/app/thumbnail_cache
      - ~/config.cfg:/app/config/config.cfg
      - ~/gramps_db:/root/.gramps/grampsdb
      - ~/gramps_media:/app/media

volumes:
  gramps_users:
  gramps_index:
  gramps_thumb_cache:
```

This will generate three named volumes to make sure that the user database, search index, and thumbnail cache will persist, and will mount the configuration file, Gramps database directory, and the directory holding your media files into the container (the paths on the left-hand side of the colon `:` refer to your host machine, the ones on the right hand side to the container and should not be changed).

!!! warning
    The above will make the API available on port 80 of the host machine **without SSL/TLS protection**. You can use this for local testing, but do not expose this directly to the internet, it is completely insecure!



## Step 5: Securing access with SSL/TLS

The web API **must** be served to the public internet over HTTPS. There are several options, e.g.

- Using docker hosting that includes SSL/TLS automatically
- Using an Nginx Reverse Proxy with a Let's Encrypt certificate

A particularly convenient option is to use a dockerized Nginx reverse proxy with automated Let's Encrypt certificate generation. This is achieved with the following `docker-compose.yml`:

```yaml
version: "3.7"

services:
  gramps_webapi:
    image: dmstraub/gramps-webapi:latest
    restart: always
    environment:
      - VIRTUAL_PORT=5000
      - VIRTUAL_HOST=...  # e.g. gramps.mydomain.com
      - LETSENCRYPT_HOST=...   # e.g. gramps.mydomain.com
      - LETSENCRYPT_EMAIL=...  # your email
    volumes:
      - gramps_users:/app/users
      - gramps_index:/app/indexdir
      - gramps_thumb_cache:/app/thumbnail_cache
      - ~/config.cfg:/app/config/config.cfg
      - ~/gramps_db:/root/.gramps/grampsdb
      - ~/gramps_media:/app/media
    networks:
      - proxy-tier
      - default

  proxy:
    image: nginxproxy/nginx-proxy
    restart: always
    ports:
      - 80:80
      - 443:443
    environment:
      - ENABLE_IPV6=true
    volumes:
      - conf:/etc/nginx/conf.d
      - dhparam:/etc/nginx/dhparam
      - certs:/etc/nginx/certs:ro
      - vhost.d:/etc/nginx/vhost.d
      - html:/usr/share/nginx/html
      - /var/run/docker.sock:/tmp/docker.sock:ro
    networks:
      - proxy-tier

  acme-companion:
    image: nginxproxy/acme-companion
    container_name: nginx-proxy-acme
    restart: always
    volumes_from:
      - proxy
    volumes:
      - certs:/etc/nginx/certs:rw
      - acme:/etc/acme.sh
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - proxy-tier
    depends_on:
      - proxy

volumes:
  acme:
  certs:
  conf:
  dhparam:
  vhost.d:
  html:
  gramps_users:
  gramps_index:
  gramps_thumb_cache:

networks:
  proxy-tier:
```

Please see the [acme-companion](https://github.com/nginx-proxy/acme-companion) docs for how to set up your domain.
