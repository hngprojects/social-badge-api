"""add access_code to badges

Revision ID: 139e5cfb4283
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 21:24:41.552093

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "139e5cfb4283"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "badges", sa.Column("access_code", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("badges", "access_code")
