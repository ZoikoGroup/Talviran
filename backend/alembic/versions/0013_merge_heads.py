"""0013 merge dual 0012 heads

Combines the two 0012 migrations that branched off migration 0011
(c7e4a1b9d602):

  - 0150dc1bec31 — supabase-backed credentials (dropped password_hash,
    added supabase_user_id)
  - a1f3c9b7e2d4 — evidence_bundle research_message_id link

Neither migration touches the same tables or columns, so this merge
migration is a no-op — it exists solely to collapse the two heads back
into a single linear chain.

Revision ID: 0013_merge_heads
Revises: 0150dc1bec31, a1f3c9b7e2d4
Create Date: 2026-09-16
"""

from collections.abc import Sequence

revision: str = "0013_merge_heads"
down_revision: str | Sequence[str] | None = ("0150dc1bec31", "a1f3c9b7e2d4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
