# Multi-platform official Python manifest pinned, verified from registry-1.docker.io.
FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db

# Debian snapshot and a fixed font package keep Chinese chart rendering reproducible.
RUN printf 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20250501T000000Z bookworm main\n' > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk=1:20220127+repack1-1 fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 analyst && useradd -M -u 10001 -g analyst analyst \
    && mkdir -p /input /output /opt/finance \
    && chmod 755 /input /output

COPY requirements.lock /opt/finance/requirements.lock
RUN --mount=type=bind,source=wheelhouse,target=/wheels,readonly pip install --no-cache-dir --no-index --find-links=/wheels --only-binary=:all: -r /opt/finance/requirements.lock \
    && pip check \
    && python -c "import numpy,pandas,scipy,matplotlib,seaborn,statsmodels,sklearn,openpyxl"
COPY entrypoint.py /opt/finance/entrypoint.py
ENV HOME=/tmp MPLCONFIGDIR=/tmp/matplotlib MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
USER 10001:10001
WORKDIR /output
ENTRYPOINT ["python", "-I", "/opt/finance/entrypoint.py"]
