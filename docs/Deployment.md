To deploy your family tree with the Gramps Web API to the web, the most convenient option at present is to use Docker.

## Deploy with docker

A continuously updated image with all the necessary ingredients is provided on [Docker Hub](https://hub.docker.com/r/dmstraub/gramps-webapi). You can run it with 

```
docker run -d --name=gramps_webapi --restart=always \
  -v gramps_users:/app/users \
  -v gramps_index:/app/indexdir \
  -v gramps_thumb_cache:/app/thumbnail_cache \
  -v /path/to/config.cfg:/app/config/config.cfg \
  -v /path/to/grampsdb:/root/.gramps/grampsdb \
  -v /path/to/gramps_media:/app/media \
  -p 80:5000 \
  dmstraub/gramps-webapi:latest
```

This will generate three named volumes to make sure that the user database, search index, and thumbnail cache will persist, and will mount the configuration file, Gramps database directory, and the directory holding your media files into the container (the paths on the left-hand side of the colon `:` refer to your host machine, the ones on the right hand side to the container and should not be changed). Equivalently, you can use `docker-compose` with the following `docker-compose.yaml`:

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
      - /path/to/config.cfg:/app/config/config.cfg
      - /path/to/grampsdb:/root/.gramps/grampsdb
      - /path/to/gramps_media:/app/media 

volumes:
  gramps_users:
  gramps_index:
  gramps_thumb_cache:
```


The configuration file should contain at least the following lines:

```python
TREE="..."  # set the name of your family tree
SECRET_KEY="..." # set your secret key
# do not change the following lines as they refer to paths within the container
USER_DB_URI="sqlite:////app/users/users.sqlite"
MEDIA_BASE_DIR="/app/media"
SEARCH_INDEX_DIR="/app/indexdir"
STATIC_PATH="/app/static"
```

For other configuration options, see [Configuration](Configuration).

Note that the above will make the API available on port 80 of the host machine **without SSL/TLS protection**. You can use this for local testing, but do not expose this directly to the internet, it is completely insecure!

## Securing access with SSL/TLS

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
      - /path/to/config.cfg:/app/config/config.cfg  # set the path before ':'
      - /path/to/grampsdb:/root/.gramps/grampsdb  # set the path before ':'
      - /path/to/gramps_media:/app/media   # set the path before ':'
    networks:
      - proxy-tier
      - default

  proxy:
    image: jwilder/nginx-proxy
    restart: always
    ports:
      - 80:80
      - 443:443
    environment:
      - ENABLE_IPV6=true
    labels:
      com.github.jrcs.letsencrypt_nginx_proxy_companion.nginx_proxy: "true"
    volumes:
      - certs:/etc/nginx/certs:ro
      - vhost.d:/etc/nginx/vhost.d
      - html:/usr/share/nginx/html
      - /var/run/docker.sock:/tmp/docker.sock:ro
    networks:
      - proxy-tier

  letsencrypt-companion:
    image: jrcs/letsencrypt-nginx-proxy-companion
    restart: always
    volumes:
      - certs:/etc/nginx/certs
      - vhost.d:/etc/nginx/vhost.d
      - html:/usr/share/nginx/html
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - proxy-tier
    depends_on:
      - proxy

volumes:
  certs:
  vhost.d:
  html:
  gramps_users:
  gramps_index:
  gramps_thumb_cache:

networks:
  proxy-tier:
```

Please see the [Let's Encrypt Companion](https://hub.docker.com/r/jrcs/letsencrypt-nginx-proxy-companion/) docs for how to set up your domain.