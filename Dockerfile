FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_DEBUG=1 DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput && chmod -R a+rX /app
USER 10001
EXPOSE 8000
CMD ["gunicorn", "dashboard.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--graceful-timeout", "30"]
