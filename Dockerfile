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
# The LEAN file, deliberately not requirements.txt. requirements.txt carries the test tooling
# because the platform's generated pipeline installs it before running pytest; shipping pytest,
# coverage and httpx in the runtime image would add CVE surface the container never executes.
COPY requirements-runtime.txt ./
RUN pip install --require-hashes --no-deps -r requirements-runtime.txt

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

# The training content tree: procedures, scenario templates, rubrics, expert traces. DATA the
# server reads, so it is baked in rather than fetched, and deliberately NOT chowned to the
# application user. Root-owned and world-readable means the process can read its own scoring
# rules and can never rewrite them, which is the same fail-closed posture the storage probe
# takes. Changing content is a deploy or an overlay mount, never a running process writing to
# itself. Placed BEFORE the sweep below, because nothing may follow it.
COPY content ./content

# Fail-CLOSED: strip the package manager and every build artefact from what ships, THEN clear
# every setuid and setgid bit. One instruction, two fail-closed steps, in that order.
#
# They were two consecutive `RUN`s and the platform's Dockerfile linter flagged the pair. Merging
# them keeps the invariant that matters - the suid sweep is still the LAST filesystem mutation in
# this stage, now as the last command of the last RUN - while removing the smell. What must never
# happen is an instruction AFTER the sweep re-introducing the class it cleared, and three contract
# tests enforce exactly that.
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
           /usr/bin/apt /usr/bin/apt-get /usr/bin/apt-cache /usr/bin/apt-config \
           /usr/bin/apt-key /usr/bin/apt-mark /usr/bin/aptitude \
           /usr/bin/dpkg /usr/bin/dpkg-deb /usr/bin/dpkg-divert /usr/bin/dpkg-query \
           /usr/bin/dpkg-split /usr/bin/dpkg-statoverride /usr/bin/dpkg-trigger \
           /usr/bin/dpkg-maintscript-helper /usr/sbin/dpkg-preconfigure \
           /etc/apt /usr/lib/apt \
           /usr/local/lib/python3.12/ensurepip \
           /var/lib/apt/lists/* /var/cache/apt/* /root/.cache /tmp/* \
 && find / -xdev -perm /6000 \( -type f -o -type d \) -exec chmod a-s {} +

# ensurepip is removed for a reason a PATH check cannot see. It is not a binary, so
# `command -v pip` reports nothing, but it vendors a complete pip WHEEL
# (pip-25.0.1-py3-none-any.whl) that a filesystem CVE scanner reports as a shipped package.
# The claim "no package manager ships" was false because of it. Found by the CI image job on
# its first ever run, having been hypothesised by a reviewer who could not settle it without a
# build. The runtime never calls ensurepip: the venv is built in an earlier stage.
#
# NOTE on what is deliberately KEPT: /var/lib/dpkg stays. It is the package DATABASE, not
# a tool, and it is what the platform's image policy scan reads to enumerate the OS
# packages present. Deleting it would remove the scanner's evidence rather than the risk,
# which is suppressing a finding rather than addressing it, and that is forbidden. The
# tools come out; the truth about what ships stays in.

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
# Probes the LIVENESS path, not readiness. A Docker HEALTHCHECK is a liveness signal, and
# any runtime that acts on it restarts an unhealthy container, so pointing it at a
# readiness path would restart the pod on a storage fault: exactly the coupling the split
# paths exist to prevent. The PLATFORM readiness probe is configured on /healthz, which
# carries the real-write proof and the diagnostic 503 (see docs/DEPLOYMENT.md).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-m", "enlightenment.healthcheck"]
# `exec` so SIGTERM reaches gunicorn and shutdown does not hang. `-b 0.0.0.0:${PORT:-8080}`
# is load-bearing: gunicorn and uvicorn default to 127.0.0.1, which the platform probe
# cannot reach.
# ONE worker, deliberately. The training snapshot is a file-backed read-modify-write
# store. The store now serialises writes with an exclusive advisory lock and guards them
# with a revision, so more than one writer is safe by construction; a single worker keeps
# it safe even where advisory locking does not hold, such as some network mounts, and the
# workload is asynchronous and input-output bound, so a second process buys nothing
# measurable. Two workers were measured losing half of all acknowledged writes.
CMD ["sh", "-c", "exec gunicorn enlightenment.asgi:app -k uvicorn.workers.UvicornWorker -b \"0.0.0.0:${PORT:-8080}\" --workers 1 --timeout 60 --access-logfile - --error-logfile -"]
