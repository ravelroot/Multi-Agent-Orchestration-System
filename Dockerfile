FROM node:22-alpine AS interface
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APOGEU_HOST=0.0.0.0 APOGEU_DATA_DIR=/dados
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 1000 apogeu && mkdir /dados && chown apogeu /dados
COPY VERSION ./
COPY apogeu ./apogeu
COPY --from=interface /app/frontend/out ./frontend/out
USER apogeu
EXPOSE 8000
VOLUME ["/dados"]
CMD ["python", "-m", "apogeu"]
