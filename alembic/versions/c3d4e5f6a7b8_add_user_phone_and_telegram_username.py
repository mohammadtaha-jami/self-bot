"""add users.phone_number and users.telegram_username

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(length=100), nullable=True))
    op.execute(
        sa.text(
            "UPDATE users SET phone_number = username "
            "WHERE phone_number IS NULL AND username IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_username")
    op.drop_column("users", "phone_number")
