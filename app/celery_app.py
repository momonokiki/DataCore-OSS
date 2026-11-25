from celery import Celery

import app.db_all_models
from app.core.config import settings


print("=== [Celery Config] Initializing Celery App ===")

# Celery application instance
celery_app = Celery(
    "datacore_tasks",
    broker=settings.CELERY_BROKER_URL,
)

# Result backend
RESULT_BACKEND_URL = settings.CELERY_BROKER_URL.replace(
    "sqla+postgresql://",
    "db+postgresql://",
)

# Celery configuration
celery_app.conf.update(
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    result_backend=RESULT_BACKEND_URL,
    worker_send_task_events=True,
    broker_transport_options={},
)

