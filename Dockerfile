FROM dmstraub/gramps:latest

WORKDIR /app
ENV PYTHONPATH="${PYTHONPATH}:/usr/lib/python3/dist-packages"

# install poppler (needed for PDF thumbnails)
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*

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

# install gunicorn
RUN python3 -m pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    gunicorn

# copy package source and install
COPY . /app/src
RUN python3 -m pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    /app/src

EXPOSE 5000

CMD gunicorn -w 8 -b 0.0.0.0:5000 gramps_webapi.wsgi:app --timeout 120
