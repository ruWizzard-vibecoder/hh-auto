"""Add last_touched_at to resumes table.

Revision ID: 001
Revises:
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resumes", "last_touched_at")
