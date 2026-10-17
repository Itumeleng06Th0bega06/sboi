#!/usr/bin/env python
"""Run Django management commands with the production settings, no terminal.

cPanel's "Setup Python App" controls are awkward for one-off commands: the
"Run Python script" field may not accept arguments, and a Cron job runs a
single line with no shell state, so an earlier
``export DJANGO_SETTINGS_MODULE=sboi.settings_prod`` never reaches the command.
The result is that Django silently falls back to ``sboi.settings`` (the
development settings) and e.g. ``collectstatic`` dies with::

    You're using the staticfiles app without having set the STATIC_ROOT
    setting to a filesystem path.

This wrapper removes that whole class of mistake: it loads the project, forces
``sboi.settings_prod`` and then runs the command you asked for.

Usage
-----
Point cPanel -> Setup Python App -> "Run Python script" at ``manage_prod.py``
(no arguments needed), or pass a command if the field allows arguments::

    manage_prod.py                      # migrate, then collectstatic
    manage_prod.py ensure_superuser
    manage_prod.py check --deploy

With no arguments it runs the whole "publish" step — ``migrate`` followed by
``collectstatic`` — which is everything that normally has to happen after a
deploy. Both commands are idempotent, so running it again is always safe.
"""
import os
import sys
from pathlib import Path

# Make sure "sboi" and the apps are importable no matter the working directory.
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

# Force the production settings module (never inherit the development default).
os.environ['DJANGO_SETTINGS_MODULE'] = 'sboi.settings_prod'

try:
    from django.core.management import execute_from_command_line
except ImportError:
    print('ERROR: Django is not importable. Run this script with the virtualenv '
          'Python created by cPanel -> Setup Python App.')
    sys.exit(1)

args = sys.argv[1:]

# No arguments = the full publish step: create/update the database schema, then
# refresh the static files. Both are safe to run repeatedly.
commands = [args] if args else [['migrate', '--noinput'], ['collectstatic', '--noinput']]

print(f'[manage_prod] DJANGO_SETTINGS_MODULE={os.environ["DJANGO_SETTINGS_MODULE"]}')
for command in commands:
    print(f'[manage_prod] running: manage.py {" ".join(command)}')
    execute_from_command_line(['manage.py', *command])
