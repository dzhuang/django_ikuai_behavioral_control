#!/bin/bash

python manage.py makemigrations
python manage.py migrate --noinput

python manage.py createsuperuser --no-input

(gunicorn behavioral_control.wsgi --user pc_user --bind 0.0.0.0:8010 --workers 3) &
sudo nginx
