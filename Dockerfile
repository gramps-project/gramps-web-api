FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV GRAMPS_VERSION=52

WORKDIR /app

ENV PYTHONPATH="${PYTHONPATH}:/usr/lib/python3/dist-packages"

# install poppler (needed for PDF thumbnails)
# ffmpeg (needed for video thumbnails)
# postgresql client (needed for PostgreSQL backend)
RUN apt-get update && apt-get install -y \
  appstream pkg-config libcairo2-dev \
  gir1.2-gtk-3.0 libgirepository1.0-dev libicu-dev \
  graphviz gir1.2-gexiv2-0.10 gir1.2-osmgpsmap-1.0 \
  locales gettext wget python3-pip python3-pil \
  poppler-utils ffmpeg libavcodec-extra \
  unzip \
  libpq-dev postgresql-client postgresql-client-common python3-psycopg2 \
  libgl1-mesa-dev libgtk2.0-dev libatlas-base-dev \
  libopencv-dev python3-opencv \
  tesseract-ocr tesseract-ocr-all \
  libopenblas-dev \
  && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \
  && rm -rf /var/lib/apt/lists/*

# set locale
RUN localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANGUAGE en_US.utf8
ENV LANG en_US.utf8
ENV LC_ALL en_US.utf8

ENV GRAMPS_API_CONFIG=/app/config/config.cfg

# create directories
RUN mkdir /app/src &&  mkdir /app/config && touch /app/config/config.cfg
RUN mkdir /app/static && touch /app/static/index.html
RUN mkdir /app/db && mkdir /app/media && mkdir /app/indexdir && mkdir /app/users
RUN mkdir /app/thumbnail_cache
RUN mkdir /app/cache && mkdir /app/cache/reports && mkdir /app/cache/export
RUN mkdir /app/tmp && mkdir /app/persist
RUN mkdir -p /root/.gramps/gramps$GRAMPS_VERSION/plugins
# set config options
ENV GRAMPSWEB_USER_DB_URI=sqlite:////app/users/users.sqlite
ENV GRAMPSWEB_MEDIA_BASE_DIR=/app/media
ENV GRAMPSWEB_SEARCH_INDEX_DB_URI=sqlite:////app/indexdir/search_index.db
ENV GRAMPSWEB_STATIC_PATH=/app/static
ENV GRAMPSWEB_THUMBNAIL_CACHE_CONFIG__CACHE_DIR=/app/thumbnail_cache
ENV GRAMPSWEB_REPORT_DIR=/app/cache/reports
ENV GRAMPSWEB_EXPORT_DIR=/app/cache/export

# install PostgreSQL addon
RUN wget https://github.com/gramps-project/addons/archive/refs/heads/master.zip \
    && unzip -p master.zip addons-master/gramps$GRAMPS_VERSION/download/PostgreSQL.addon.tgz | \
    tar -xvz -C /root/.gramps/gramps$GRAMPS_VERSION/plugins \
    && unzip -p master.zip addons-master/gramps$GRAMPS_VERSION/download/SharedPostgreSQL.addon.tgz | \
    tar -xvz -C /root/.gramps/gramps$GRAMPS_VERSION/plugins \
    && unzip -p master.zip addons-master/gramps$GRAMPS_VERSION/download/FilterRules.addon.tgz | \
    tar -xvz -C /root/.gramps/gramps$GRAMPS_VERSION/plugins \
    && rm master.zip

# install gunicorn
RUN python3 -m pip install --break-system-packages --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    gunicorn

# Install PyTorch based on architecture
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "armv7l" ]; then \
        # Install the armv7l-specific PyTorch wheel
        python3 -m pip install --break-system-packages --no-cache-dir \
        https://github.com/maxisoft/pytorch-arm/releases/download/v1.0.0/torch-1.13.0a0+git7c98e70-cp311-cp311-linux_armv7l.whl; \
    else \
        # Install PyTorch from the official index for other architectures
        python3 -m pip install --break-system-packages --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch; \
    fi

# copy package source and install
COPY . /app/src
RUN python3 -m pip install --break-system-packages --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    scikit-learn==1.4.2 numpy==1.26.4 /app/src[ai]

# download and cache sentence transformer model
RUN python3 -c "\
from sentence_transformers import SentenceTransformer; \
model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')"

EXPOSE 5000

COPY docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD gunicorn -w ${GUNICORN_NUM_WORKERS:-8} -b 0.0.0.0:5000 gramps_webapi.wsgi:app --timeout 120 --limit-request-line 8190
