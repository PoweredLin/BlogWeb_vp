FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY vite.source.config.mjs vite.tools.config.mjs ./
COPY source ./source
COPY scripts/build.mjs ./scripts/build.mjs
RUN npm run build

FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY backend/requirements.lock.txt ./backend/requirements.lock.txt
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r backend/requirements.lock.txt && useradd --uid 10001 --create-home notebook
COPY backend ./backend
COPY public ./public
COPY --from=build /app/public ./public
RUN mkdir -p /app/data/uploads /app/backups && chown -R notebook:notebook /app/data /app/backups
USER notebook
ENV APP_ENV=production HOST=0.0.0.0 PORT=4317 DATA_DIR=/app/data
EXPOSE 4317
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4317/healthz',timeout=3)"
CMD ["python","-m","backend.run"]
