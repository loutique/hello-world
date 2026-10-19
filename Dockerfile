FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
COPY .wheelhouse /wheels
ARG OFFLINE_BUILD=0
RUN if [ "$OFFLINE_BUILD" = "1" ]; then pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
RUN rm -rf /wheels
COPY . .
RUN DJANGO_SECRET_KEY=build-only USE_SQLITE=1 python manage.py collectstatic --noinput
RUN useradd --create-home app && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["sh", "scripts/start-web.sh"]
