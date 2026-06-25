from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.workers.digest_jobs import send_daily_digests, send_weekly_reports


class WorkerSettings:
    """
    arq worker configuration settings.

    Purpose:
        Configures the arq Redis background worker settings,
        defining the Redis connection parameters and setting up cron schedules
        for periodic jobs like daily digests and weekly reports.

    Authentication Context:
        None.
        Executed in the background by the arq CLI system process.

    Performance Implications:
        Uses a shared Redis connection pool.
        Cron job execution times should be staggered if resource utilization spikes.

    Rate Limiting:
        Governed by cron schedule definitions (daily_digest at 20:00 UTC daily,
        weekly_report at 20:00 UTC Sundays).

    Dependencies:
        Depends on `settings.REDIS_URL`, `send_daily_digests`,
        and `send_weekly_reports`.
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
