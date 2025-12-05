FROM mcr.microsoft.com/devcontainers/python:3.11

ENV GRAMPSHOME=/home/vscode
ENV GRAMPS_VERSION=60

RUN apt-get update && apt-get install -y \
  gettext appstream pkg-config libcairo2-dev gir1.2-gtk-3.0 \
  gir1.2-gexiv2-0.10 gir1.2-osmgpsmap-1.0 poppler-utils \
  libgirepository1.0-dev libicu-dev libopencv-dev tesseract-ocr \
  tesseract-ocr-all gir1.2-pango-1.0 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install opencv-python
RUN pip install gramps==6.0.4

# Install Gramps addons (FilterRules for DegreesOfSeparation filter)
RUN mkdir -p $GRAMPSHOME/gramps/gramps$GRAMPS_VERSION/plugins && \
    wget https://github.com/gramps-project/addons/archive/refs/heads/master.zip && \
    for addon in FilterRules; do \
        unzip -p master.zip addons-master/gramps$GRAMPS_VERSION/download/$addon.addon.tgz | \
        tar -xvz -C $GRAMPSHOME/gramps/gramps$GRAMPS_VERSION/plugins; \
    done && \
    rm master.zip && \
    chown -R vscode:vscode $GRAMPSHOME/gramps

# CPU-only version of PyTorch
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install sentence-transformers

# download and cache sentence transformer model
RUN python3 -c "from sentence_transformers import SentenceTransformer; \
model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')";

