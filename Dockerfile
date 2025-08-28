FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Minimum system packages (sometimes wheel is enough without this;
# if something crashes during assembly - leave build-essential)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Put only the manifest so that the layers are cached
COPY pyproject.toml ./

# Install uv, compile dependencies into a lock file and install them
RUN pip install --upgrade pip uv \
 && uv pip compile pyproject.toml -o requirements.lock \
 && uv pip install --system -r requirements.lock

# Now we put the code \
COPY . .

EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
