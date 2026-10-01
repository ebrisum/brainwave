# syntax=docker/dockerfile:1.7
# Two targets: `api` (FastAPI, no Blender) and `worker` (gpx2course + headless Blender LTS + gltfpack + KTX tools).

FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY gpx2course ./gpx2course
COPY api ./api
COPY blender ./blender
RUN pip install ".[api]"

FROM base AS api
ENV RIDEPREP_COURSES_DIR=/data/courses
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM base AS worker
# Blender LTS, pinned (verify the exact patch release at build time: https://www.blender.org/download/lts/)
ARG BLENDER_VERSION=5.2.0
ARG BLENDER_SERIES=5.2
ARG GLTFPACK_VERSION=1.3.0
ARG KTX_VERSION=4.4.0
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libgl1 libegl1 nodejs npm \
    && curl -fsSL "https://download.blender.org/release/Blender${BLENDER_SERIES}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" | tar -xJ -C /opt \
    && ln -s "/opt/blender-${BLENDER_VERSION}-linux-x64/blender" /usr/local/bin/blender \
    && npm install -g "gltfpack@${GLTFPACK_VERSION}" \
    && curl -fsSL -o /tmp/ktx.deb "https://github.com/KhronosGroup/KTX-Software/releases/download/v${KTX_VERSION}/KTX-Software-${KTX_VERSION}-Linux-x86_64.deb" \
    && (apt-get install -y /tmp/ktx.deb || echo "KTX-Software not installed; textures stay uncompressed") \
    && rm -rf /var/lib/apt/lists/* /tmp/ktx.deb
ENV RIDEPREP_COURSES_DIR=/data/courses GPX2COURSE_CACHE=/data/cache
CMD ["python", "-m", "api.worker"]
