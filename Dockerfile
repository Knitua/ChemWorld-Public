FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Knitua/ChemWorld-Public"
LABEL org.opencontainers.image.description="Provider-free ChemWorld Student Lab and Agent Observatory"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=10000

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY configs ./configs

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin chemworld

USER 10001

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '10000') + '/api/health', timeout=3).read()"

CMD ["python", "-m", "chemworld.lab.server", "--public", "--host", "0.0.0.0", "--no-browser"]
