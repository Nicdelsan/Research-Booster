FROM python:3.12-slim

RUN useradd --create-home --uid 10001 rb
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
RUN pip install --no-cache-dir .

USER rb
EXPOSE 8000
CMD ["uvicorn", "--factory", "rb.api.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
