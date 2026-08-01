FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/kozmik
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
RUN --mount=type=cache,target=/root/.cache/pip pip install .

RUN useradd --system --uid 10001 --create-home kozmik \
    && mkdir -p /var/lib/kozmik /var/log/kozmik \
    && chown -R kozmik:kozmik /var/lib/kozmik /var/log/kozmik
USER 10001

EXPOSE 8000
CMD ["python", "-m", "kozmik_executor.run"]
