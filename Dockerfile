FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home app && chown -R app /usr/src/app
USER app

CMD ["python", "bot.py"]
