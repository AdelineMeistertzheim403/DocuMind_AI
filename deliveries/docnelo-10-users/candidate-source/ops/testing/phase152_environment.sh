#!/bin/bash
set -eu
cat /etc/os-release
ps -p 1 -o comm=
python3 --version
python3 -c 'import importlib.util; print({n:importlib.util.find_spec(n) is not None for n in ("sqlalchemy","psycopg","pytest")})'
systemctl --version
id
command -v docker || true
ls -l /run/docker.sock /var/run/docker.sock 2>/dev/null || true
