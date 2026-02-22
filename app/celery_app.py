from celery import Celery

celery = Celery(
    "rag_worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/1",
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Singapore",
    enable_utc=True,
)

# Ensure tasks in the app package are registered when the worker starts
celery.autodiscover_tasks(["app"])
