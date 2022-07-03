FROM dmstraub/gramps:5.1.5

ENV GRAMPS_VERSION=51
WORKDIR /app
ENV PYTHONPATH="${PYTHONPATH}:/usr/lib/python3/dist-packages"

# install poppler (needed for PDF thumbnails)
# ffmpeg (needed for video thumbnails)
# postgresql client (needed for PostgreSQL backend)
RUN apt-get update && apt-get install -y \
  poppler-utils ffmpeg libavcodec-extra \
  unzip \
  libpq-dev postgresql-client postgresql-client-common python3-psycopg2 \
  python3-opencv \
  && rm -rf /var/lib/apt/lists/*

# set locale
RUN localedef -i en_GB -c -f UTF-8 -A /usr/share/locale/locale.alias en_GB.UTF-8
ENV LANGUAGE en_GB.utf8
ENV LANG en_GB.utf8
ENV LC_ALL en_GB.utf8

ENV GRAMPS_API_CONFIG=/app/config/config.cfg

# create directories
RUN mkdir /app/src &&  mkdir /app/config && touch /app/config/config.cfg
RUN mkdir /app/static && touch /app/static/index.html
RUN mkdir /app/db && mkdir /app/media && mkdir /app/indexdir && mkdir /app/users
RUN mkdir /app/thumbnail_cache
RUN mkdir /app/tmp
RUN mkdir -p /root/.gramps/gramps$GRAMPS_VERSION
ENV USER_DB_URI=sqlite:////app/users/users.sqlite
ENV MEDIA_BASE_DIR=/app/media
ENV SEARCH_INDEX_DIR=/app/indexdir
ENV STATIC_PATH=/app/static

# install PostgreSQL addon
RUN wget https://github.com/gramps-project/addons/archive/refs/heads/master.zip \
    && unzip -p master.zip addons-master/gramps$GRAMPS_VERSION/download/PostgreSQL.addon.tgz | \
    tar -xvz -C /root/.gramps/gramps$GRAMPS_VERSION/plugins && rm master.zip

# install gunicorn
RUN python3 -m pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    gunicorn

# copy package source and install
COPY . /app/src
RUN python3 -m pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    /app/src

EXPOSE 5000

COPY docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD gunicorn -w ${GUNICORN_NUM_WORKERS:-8} -b 0.0.0.0:5000 gramps_webapi.wsgi:app --timeout 120 --limit-request-line 8190
