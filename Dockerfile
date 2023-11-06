FROM python:3.11-slim

ENV POETRY_VERSION=1.5.0 \
    PIP_NO_CACHE_DIR=1

WORKDIR /backend/

RUN pip install -U poetry

COPY ./pyproject.toml ./poetry.lock* ./

RUN poetry install --no-root --without dev

COPY . .

ENTRYPOINT ["./scripts/entrypoint.sh"]
