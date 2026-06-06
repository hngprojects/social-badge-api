"""rename notification_type badge_creation to badge_alert

Revision ID: a1b2c3d4e5f6
Revises: 4ddef85825ad
Create Date: 2026-06-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "4ddef85825ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add the new enum value
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'badge_alert'")
    # Commit the enum change (ALTER TYPE ADD VALUE cannot run inside a transaction)
    op.execute("COMMIT")
    # Update existing rows from the old enum label to the new value
    op.execute(
        "UPDATE notifications SET type = 'badge_alert' WHERE type = 'BADGE_CREATION'"
    )


def downgrade() -> None:
    # Revert rows back to the old value
    op.execute(
        "UPDATE notifications SET type = 'BADGE_CREATION' WHERE type = 'badge_alert'"
    )
    # Note: PostgreSQL does not support removing values from an existing enum type.
    # The 'badge_alert' value will remain in the enum but will no longer be used.
