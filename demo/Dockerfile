FROM dmstraub/gramps-webapi:latest

# copy config file
COPY config.cfg /app/config/

# create non-root user and grant privileges
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# extract & use Gramps example tree
ENV GRAMPS_RESOURCES /usr/share/
RUN cp -r /usr/share/doc/gramps/example/gramps/example.gramps.gz .
RUN gunzip example.gramps.gz
RUN gramps -C Example -i example.gramps --config=database.backend:sqlite --config=database.path:/app/.gramps/grampsdb
RUN rm -rf appcache

# build full-text search index
RUN python3 -m gramps_webapi  --config /app/config/config.cfg search index-full

# the $PORT variable is needed for Heroku
CMD gunicorn -w 2 -b 0.0.0.0:$PORT gramps_webapi.wsgi:app --timeout 120

