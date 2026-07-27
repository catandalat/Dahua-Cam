"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-07-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created via SQLAlchemy metadata.create_all on API startup.
    # This revision exists so Alembic is wired; stamp it after first boot:
    #   alembic -c infra/alembic.ini stamp head
    pass


def downgrade() -> None:
    pass
