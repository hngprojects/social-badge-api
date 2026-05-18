from datetime import datetime, timezone
import logging

from services.badges.db.session import SessionLocal
from services.badges.models.badge_model import BadgeGenerationJob
from services.badges.enums.job_status import JobStatus

from services.badges.services.renderer import generate_badge_image
from services.badges.services.img_service import save_image

logger = logging.getLogger(__name__)


def process_badge_generation(job_id: str):
    """Process badge generation job: render image, save it, and update job status."""

    db = SessionLocal()

    try:
        # Query using string job_id (stored as string in SQLite)
        job = db.query(BadgeGenerationJob).filter(
            BadgeGenerationJob.job_id == job_id
        ).first()

        if not job:
            logger.warning(f"Job {job_id} not found")
            return

        job.status = JobStatus.PROCESSING
        db.commit()
        logger.info(f"Processing job {job_id}")

        # render
        image_buffer = generate_badge_image(
            job.participant_photo_url
        )

        # save image
        url = save_image(
            image_buffer,
            filename=f"badge_{job_id}.png"
        )

        # update DB
        job.status = JobStatus.COMPLETED
        job.badge_image_url = url
        job.completed_at = datetime.now(timezone.utc)

        db.commit()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}", exc_info=True)
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        db.commit()

    finally:
        db.close()