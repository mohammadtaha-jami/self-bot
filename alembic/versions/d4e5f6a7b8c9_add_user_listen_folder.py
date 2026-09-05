"""add users.listen_folder_id and listen_folder_title

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("listen_folder_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("listen_folder_title", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "listen_folder_title")
    op.drop_column("users", "listen_folder_id")
