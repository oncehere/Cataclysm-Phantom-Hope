FROM docker.io/library/python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d

# Snapshot repository + exact package versions keep gettext resolution stable.
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf '%s\n' 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20250915T000000Z bookworm main' > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gettext=0.21-12 gettext-base=0.21-12 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/pokeeper
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY src ./src
COPY pyproject.toml README.md LICENSE ./
# A small pure-Python package: same module CLI without extra build dependencies.
ENV PYTHONPATH=/opt/pokeeper/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /work
ENTRYPOINT ["python", "-m", "pokeeper"]
CMD ["--help"]
