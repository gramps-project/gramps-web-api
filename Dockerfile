FROM ghcr.io/gramps-project/gramps-web-base:latest

ENV GRAMPS_API_CONFIG=/app/config/config.cfg

# create directories
RUN mkdir /app/src &&  mkdir /app/config && touch /app/config/config.cfg
RUN mkdir /app/static && touch /app/static/index.html
RUN mkdir /app/db && mkdir /app/media && mkdir /app/indexdir && mkdir /app/users
RUN mkdir /app/thumbnail_cache
RUN mkdir /app/cache && mkdir /app/cache/reports && mkdir /app/cache/export \
    && mkdir /app/cache/request_cache && mkdir /app/cache/persistent_cache
RUN mkdir /app/tmp && mkdir /app/persist
# set config options
ENV GRAMPSWEB_USER_DB_URI=sqlite:////app/users/users.sqlite
ENV GRAMPSWEB_MEDIA_BASE_DIR=/app/media
ENV GRAMPSWEB_SEARCH_INDEX_DB_URI=sqlite:////app/indexdir/search_index.db
ENV GRAMPSWEB_STATIC_PATH=/app/static
ENV GRAMPSWEB_THUMBNAIL_CACHE_CONFIG__CACHE_DIR=/app/thumbnail_cache
ENV GRAMPSWEB_REQUEST_CACHE_CONFIG__CACHE_DIR=/app/cache/request_cache
ENV GRAMPSWEB_PERSISTENT_CACHE_CONFIG__CACHE_DIR=/app/cache/persistent_cache
ENV GRAMPSWEB_REPORT_DIR=/app/cache/reports
ENV GRAMPSWEB_EXPORT_DIR=/app/cache/export
ENV GRAMPSHOME=/root
ENV GRAMPS_DATABASE_PATH=/root/.gramps/grampsdb

# copy package source and install
COPY . /app/src
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    /app/src[ai]

# download and cache YFull tree for yclade
RUN python3 -c "import yclade; yclade.tree.download_yfull_tree()"

EXPOSE 5000

COPY docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD gunicorn -w ${GUNICORN_NUM_WORKERS:-8} -b 0.0.0.0:5000 gramps_webapi.wsgi:app --timeout ${GUNICORN_TIMEOUT:-120} --limit-request-line 8190
