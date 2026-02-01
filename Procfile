web: python manage.py migrate && gunicorn bloodbankmanagement.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A bloodbankmanagement worker --loglevel=info