# syntax=docker/dockerfile:1
# SOURCE-ONLY (M2-T1 / PG-A). This file authorizes no build, push, deploy or
# runtime change. Proposal only; cutover is a separate gate (PG-D).
#
# Base pin: python:3.12-slim, multi-arch index digest (registry-verified
# 2026-10-23 read-only from manifest + config; image not pulled).
# PATCH DELTA -- NOT exact parity: base PYTHON_VERSION=3.12.15, live UI runs
# 3.12.3. Same minor line; re-assess before any cutover.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# procps is OS-level parity for the app's existing `ps aux` call
# (dashboard/views.py), not a Python dependency change. `tail` is coreutils,
# already in the base. No compiler or toolchain is installed.
RUN apt-get update \
 && apt-get install -y --no-install-recommends procps \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/car_ads_dashboard

# Dependencies first, application after: a code-only change then reuses this
# layer. The 154 pins are installed unchanged -- no slimming, no additions.
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.txt && rm -f /tmp/requirements.txt
COPY car_ads_dashboard/ /app/car_ads_dashboard/

# Explicit runtime identity: UID/GID 1000, no root, no dynamic user, no sudo.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin app \
 && chown -R 1000:1000 /app
USER 1000:1000

# One Daphne, exact loopback bind, ASGI app only. No gunicorn, WhiteNoise,
# worker/beat/redis, no migrate, no collectstatic. Static is served by the
# existing ASGIStaticFilesHandler path (DJANGO_SERVE_STATIC), which resolves
# files through the staticfiles finders over the copied source tree.
CMD ["daphne", "-b", "127.0.0.1", "-p", "18111", "car_ads_dashboard.asgi:application"]
