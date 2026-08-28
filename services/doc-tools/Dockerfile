FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    file \
    libgl1 \
    libglib2.0-0 \
    libmagic1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt /app/requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /app/requirements.txt

COPY app /app

EXPOSE 9478

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9478"]
