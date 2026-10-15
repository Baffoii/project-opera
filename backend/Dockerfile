# UNTESTED: Docker is not installed on the machine this was written on. Review before relying on it.
FROM python:3.13-slim
WORKDIR /srv/backend
COPY pyproject.toml ./
COPY app ./app
COPY registry ./registry
COPY fixtures ./fixtures
# Add ",geoclip" to install the local GeoCLIP model (large: pulls torch). Without it only the mock adapter runs.
ARG EXTRAS=postgres,eval
RUN pip install --no-cache-dir ".[${EXTRAS}]"
ENV OPERA_STORAGE_DIR=/data/uploads OPERA_MODEL_CACHE_DIR=/data/model_cache
RUN useradd --create-home opera && mkdir -p /data && chown opera /data
USER opera
EXPOSE 8000
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
