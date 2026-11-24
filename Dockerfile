FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 TECHNO_BIND=0.0.0.0 TECHNO_DB=/app/data/knowledge.sqlite3
WORKDIR /app
RUN groupadd --system techno && useradd --system --gid techno techno && mkdir -p /app/data && chown techno:techno /app/data
COPY server.py database.py diagnostics.py ./
COPY public/ ./public/
USER techno
EXPOSE 8000
VOLUME ["/app/data"]
CMD ["python", "server.py"]
