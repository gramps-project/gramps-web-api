FROM mcr.microsoft.com/devcontainers/python:3.11


RUN apt-get update && apt-get install -y \
  gettext appstream pkg-config libcairo2-dev gir1.2-gtk-3.0 \
  libgirepository1.0-dev libicu-dev libopencv-dev tesseract-ocr \
  tesseract-ocr-all gir1.2-pango-1.0 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install opencv-python
RUN pip install gramps==6.0.1

ENV LANGUAGE=en
ENV OMP_NUM_THREADS=1
ENV GRAMPSWEB_USER_DB_URI=sqlite:////workspaces/web-api/data/users.sqlite
ENV GRAMPSWEB_MEDIA_BASE_DIR=/workspaces/web-api/data/media
ENV GRAMPSWEB_SEARCH_INDEX_DB_URI=sqlite:////workspaces/web-api/data/indexdir/search_index.db
ENV GRAMPSWEB_STATIC_PATH=/workspaces/web-api/data/static
ENV GRAMPSWEB_THUMBNAIL_CACHE_CONFIG__CACHE_DIR=/workspaces/web-api/data/thumbnail_cache
ENV GRAMPSWEB_REPORT_DIR=/workspaces/web-api/data/reports_cache
ENV GRAMPSWEB_EXPORT_DIR=/workspaces/web-api/data/export_cache
ENV GRAMPSHOME=/workspaces/web-api/data/
ENV GRAMPS_DATABASE_PATH=/workspaces/web-api/data/grampsdb
ENV GRAMPSWEB_TREE=Gramps\ Web
# Do not use this value in production!!
ENV GRAMPSWEB_SECRET_KEY=QAVoeYDzkQves9iDZ5PkxfdUoVElVMVYPqz-QXha6yE
ENV GRAMPSWEB_CORS_ORIGINS="*"
ENV GRAMPSWEB_VECTOR_EMBEDDING_MODEL=sentence-transformers/distiluse-base-multilingual-cased-v2
ENV GRAMPSWEB_CELERY_CONFIG__broker_url=redis://redis:6379/0
ENV GRAMPSWEB_CELERY_CONFIG__result_backend=redis://redis:6379/0

# CPU-only version of PyTorch
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install sentence-transformers

# download and cache sentence transformer model
RUN python3 -c "from sentence_transformers import SentenceTransformer; \
model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')";

