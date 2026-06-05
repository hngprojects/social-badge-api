"""arq worker for scheduled notification jobs.

Runs the daily digest and weekly report jobs on a cron schedule.

Run locally:
    uv run arq app.workers.notification_worker.WorkerSettings
"""

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.workers.digest_jobs import send_daily_digests, send_weekly_reports


class WorkerSettings:
    """arq worker configuration.

    Uses the same Redis connection as the rest of the app.

    Cron times are in UTC. Update the schedule (or add a per-org timezone
    column on User) once product confirms the desired wall-clock time.
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
