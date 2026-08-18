# No `# syntax=` frontend directive, deliberately. That directive makes the builder fetch
# an external frontend image before it reads a single instruction, and the App Store runner
# sits behind a registry mirror with no guaranteed route to public endpoints. Every feature
# used below (multi-stage, COPY --from, COPY --chown, HEALTHCHECK) is in BuildKit's built-in
# frontend, so pinning one buys nothing and adds a network dependency at build time.
# Enlightenment: hardened, flattened container for the Bluestaq App Store python template.
#
# Three stages by design:
#   build - installs the hash-locked requirements into an isolated venv, so the package
#           manager never reaches the shipped image.
#   prep  - all filesystem hygiene, ending with the suid/sgid sweep as the LAST mutation.
#   final - FROM scratch with one COPY, so the distributed image is a single clean layer.
#           The image policy scanner reads LAYER HISTORY, and a later chmod only masks a
#           bit an earlier base layer still physically carries. Flattening is the only
#           construction with no history to read.
#
# Never add ENV PORT= or ENV DATA_DIR=: code defaults carry those values and the
# platform's injected values must win.

# ---- build: install from the hash-locked requirements into an isolated venv ----------
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a AS build
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --require-hashes --no-deps -r requirements.txt

# ---- prep: hygiene only; nothing may follow the suid sweep --------------------------
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a AS prep

# Fail-OPEN step, deliberately alone in its own instruction so a tolerated miss here can
# never swallow one of the mandatory steps below.
RUN apt-get update && apt-get -y --no-install-recommends upgrade || true

# Numeric non-root user. Created BEFORE the sweep, because adding a user can set a
# setgid bit on the home directory it creates.
RUN useradd -u 10001 -r -m -s /usr/sbin/nologin appuser

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 src ./src

# Fail-CLOSED: strip the package manager and every build artefact from what ships. The
# scanner judges what is in the image, not what the entrypoint runs.
RUN rm -rf /opt/venv/lib/python3.12/site-packages/pip \
           /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.12/site-packages/setuptools \
           /opt/venv/lib/python3.12/site-packages/setuptools-*.dist-info \
           /opt/venv/lib/python3.12/site-packages/pkg_resources \
           /opt/venv/lib/python3.12/site-packages/wheel \
           /opt/venv/lib/python3.12/site-packages/wheel-*.dist-info \
           /usr/local/lib/python3.12/site-packages/pip \
           /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.12/site-packages/setuptools \
           /usr/local/lib/python3.12/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.12/site-packages/pkg_resources \
           /usr/local/lib/python3.12/site-packages/wheel \
           /usr/local/lib/python3.12/site-packages/wheel-*.dist-info \
           /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.12 \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 \
           /var/lib/apt/lists/* /var/cache/apt/* /root/.cache /tmp/*

# Fail-CLOSED and LAST: clear every setuid and setgid bit, on files AND directories. The
# policy scan stops (it does not warn) on suid_or_guid_set, and a file-only sweep misses
# the setgid directories. NOTHING may be added after this line: a later instruction can
# re-introduce the class this just cleared.
RUN find / -xdev -perm /6000 \( -type f -o -type d \) -exec chmod a-s {} +

# ---- final: one flat layer, no history for the scanner to read ----------------------
FROM scratch
COPY --from=prep / /
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-m", "enlightenment.healthcheck"]
# `exec` so SIGTERM reaches gunicorn and shutdown does not hang. `-b 0.0.0.0:${PORT:-8080}`
# is load-bearing: gunicorn and uvicorn default to 127.0.0.1, which the platform probe
# cannot reach.
CMD ["sh", "-c", "exec gunicorn enlightenment.asgi:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080} --workers 2 --timeout 60 --access-logfile - --error-logfile -"]
