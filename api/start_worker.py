"""Standalone Celery worker launcher."""
import sys
sys.path.insert(0, "/app")
from celery import Celery
from celery.apps.worker import Worker
import worker.tasks
w = Worker(app=worker.tasks.app, loglevel="info")
w.start()
