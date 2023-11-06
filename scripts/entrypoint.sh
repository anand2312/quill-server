#!/bin/bash
extra_options=""
if [[ $DEBUG != "false" ]]; then
    extra_options="--reload --reload-dir ./doodle_server"
fi

poetry run alembic upgrade head &&\
poetry run uvicorn doodle_server.app:app --host 0.0.0.0 $extra_options
