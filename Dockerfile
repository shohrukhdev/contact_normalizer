FROM python:3.13-slim

# System updates and tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
ARG APP_USER=appuser
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd -g ${APP_GID} ${APP_USER} && \
    useradd -m -u ${APP_UID} -g ${APP_GID} -s /usr/sbin/nologin ${APP_USER}

# App directory
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY normalize_contacts.py main.py /app/

# Optional: add a demo CSV so the image can run without mounts
COPY contacts_sample_open.csv /app/contacts_sample_open.csv

RUN mkdir -p /data && chown -R ${APP_USER}:${APP_USER} /data /app
VOLUME ["/data"]

USER ${APP_USER}

ENTRYPOINT ["python", "main.py"]
CMD ["contacts_sample_open.csv"]