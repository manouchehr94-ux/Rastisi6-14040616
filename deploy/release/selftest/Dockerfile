FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y --no-install-recommends python3 python3-venv python3-pip openssh-server openssh-client postgresql-16 postgresql-client-16 redis-server restic sudo ca-certificates git curl && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/test-venv
ENV PATH=/opt/test-venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1
