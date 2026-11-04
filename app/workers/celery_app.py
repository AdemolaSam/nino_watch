from celery import Celery

from app.core.config import settings
from app.workers.schedule import beat_schedule

celery_app = Celery("ninowatch", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = beat_schedule
celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["app.workers"])
