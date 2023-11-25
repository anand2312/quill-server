# quill-server

Quill is a realtime drawing and guessing game.

Try it out: https://quill-teal-omega.vercel.app \
Frontend Repo: https://github.com/NoelZak03/quill-frontend

## Setup

After cloning the repository, install dependencies with `poetry`:
```sh
poetry install
```

Install pre-commit hooks:
```sh
poetry run pre-commit install
```

Run the server with:
```sh
poetry run task server
```

Alternativaly, run the server along with the required Postgres and Redis containers with Docker:
```sh
docker compose up
```
