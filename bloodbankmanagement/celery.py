# bloodbankmanagement/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bloodbankmanagement.settings')

app = Celery('bloodbankmanagement')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Railway-optimized Celery configuration
app.conf.update(
    # Worker settings optimized for Railway
    worker_pool='solo',  # Use solo pool for Railway memory efficiency
    worker_concurrency=1,  # Single process
    worker_max_tasks_per_child=100,  # Recycle workers periodically
    worker_prefetch_multiplier=1,  # Reduce memory usage
    worker_disable_rate_limits=False,  # Keep rate limits enabled
    
    # Broker settings
    broker_pool_limit=10,
    broker_connection_max_retries=3,
    broker_connection_timeout=30,
    
    # Task settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    
    # Result backend
    result_expires=3600,  # 1 hour
    result_cache_max=1000,
    
    # Celery Beat schedule for periodic tasks
    beat_schedule={
        # Keep-alive task runs every 5 minutes to prevent Railway from stopping idle workers
        'keep-alive-every-5-minutes': {
            'task': 'blood.tasks.celery_keep_alive_task',
            'schedule': crontab(minute='*/5'),  # Every 5 minutes
            'args': (),
            'options': {'queue': 'celery'},
        },
        # Health check every hour
        'health-check-hourly': {
            'task': 'blood.tasks.debug_task',
            'schedule': crontab(minute=0, hour='*/1'),  # Every hour at minute 0
            'args': (),
            'options': {'queue': 'celery'},
        },
        # Clean up old task results daily at 2 AM
        'cleanup-task-results-daily': {
            'task': 'blood.tasks.cleanup_old_task_results',
            'schedule': crontab(minute=0, hour=2),  # Daily at 2 AM
            'args': (),
            'options': {'queue': 'celery'},
        },
    },
    beat_schedule_filename='/tmp/celerybeat-schedule',
    beat_max_loop_interval=300,  # 5 minutes
)

# Log configuration for debugging
logger.info(f"Celery app configured with broker: {app.conf.broker_url}")
logger.info(f"Celery timezone: {app.conf.timezone}")
logger.info(f"Celery beat schedule enabled: {len(app.conf.beat_schedule)} tasks")

@app.task(bind=True, name='bloodbankmanagement.celery.debug_task')
def debug_task(self):
    """
    Debug task for testing Celery setup.
    """
    logger.info(f"Debug task executed. Request: {self.request!r}")
    return {
        'status': 'success',
        'task_id': self.request.id,
        'worker': self.request.hostname,
        'timestamp': self.request.timestamp if hasattr(self.request, 'timestamp') else None
    }