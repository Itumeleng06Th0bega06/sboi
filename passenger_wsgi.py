"""Phusion Passenger entry point for cPanel ("Setup Python App").

cPanel adds this file next to your application root and points Passenger at
it. Passenger looks for a module-level ``application`` callable here.

Replace any auto-generated ``passenger_wsgi.py`` with this file.
"""
import os
import sys

# Make the project importable regardless of Passenger's working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use the production settings (MariaDB + WhiteNoise static + public_html media).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sboi.settings_prod')

from sboi.wsgi import application  # noqa: E402  (import after env setup)
