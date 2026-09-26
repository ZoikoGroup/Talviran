"""merge heads

Revision ID: d7706a4229b5
Revises: 7dafc8b52e4b, d4e5f6a7b8c9
Create Date: 2026-09-25 15:06:09.821121

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'd7706a4229b5'
down_revision: str | Sequence[str] | None = ('7dafc8b52e4b', 'd4e5f6a7b8c9')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
