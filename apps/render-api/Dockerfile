FROM rust:1.100.0-slim-bookworm AS renderer
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
RUN cargo build --release --locked

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 renderer \
    && useradd --uid 10001 --gid renderer --no-create-home renderer
WORKDIR /app
COPY apps/render-api/ /app/
# Install exactly the runtime requirements exported from uv.lock.
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps . \
    && mkdir /data && chown renderer:renderer /data
COPY --from=renderer /src/target/release/idml-render /usr/local/bin/idml-render
COPY LICENSE-APACHE LICENSE-MIT NOTICE ASSETS.md /usr/share/doc/designcraft/
COPY licenses/ /usr/share/doc/designcraft/licenses/
COPY assets/fonts/OFL-*.txt /usr/share/doc/designcraft/fonts/
COPY assets/app-icon/LICENSE.txt /usr/share/doc/designcraft/app-icon/LICENSE.txt
COPY docs/brand/LICENSE-brand.txt /usr/share/doc/designcraft/brand/LICENSE-brand.txt
ENV IDML_RENDER_BIN=/usr/local/bin/idml-render IDML_API_DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1
USER renderer
EXPOSE 8000
CMD ["python", "-m", "render_api", "--host", "0.0.0.0", "--port", "8000"]
