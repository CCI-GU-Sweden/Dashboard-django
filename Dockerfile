FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Collect optional module assets without enabling the modules at runtime.
RUN DJANGO_DEBUG=1 DJANGO_SECRET_KEY=build-only DASHBOARD_GRIDS_ENABLED=1 DASHBOARD_METROLOGY_ENABLED=1 DASHBOARD_COMPUTE_ENABLED=1 python manage.py collectstatic --noinput && chmod -R a+rX /app
USER 10001
EXPOSE 8000
CMD ["gunicorn", "dashboard.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--graceful-timeout", "30"]
