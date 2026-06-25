from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.workers.digest_jobs import send_daily_digests, send_weekly_reports


class WorkerSettings:
    """Arq worker configuration settings.

    Configures the arq Redis background worker settings, defining the Redis connection
    parameters and setting up cron schedules for periodic jobs like daily digests and
    weekly reports. Uses a shared Redis connection pool.
    """

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))

    cron_jobs = [
        cron(
            send_daily_digests,
            name="daily_digest",
            hour=20,
            minute=0,
        ),
        cron(
            send_weekly_reports,
            name="weekly_report",
            weekday="sun",
            hour=20,
            minute=0,
        ),
    ]
