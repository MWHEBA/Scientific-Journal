import sys
import os

# Dynamically set the project path relative to this file
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Journal.settings')

# Import the WSGI application
from Journal.wsgi import application
