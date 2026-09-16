"""WSGI entry point. PythonAnywhere and gunicorn both import `application` from here."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app  # noqa: E402

application = create_app()
