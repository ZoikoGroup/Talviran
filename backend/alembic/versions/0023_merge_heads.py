"""0023 merge dual heads

Combines the two heads that resulted from parallel work on ravireddy and
main both branching off 38fa495cbdf5 (0018 evaluator heartbeat):

  - 0019_merge_heads — main's own merge of the supabase-credentials chain
    with the monitoring chain, continuing through the Frankfurter/DBnomics/
    Twelve Data connector work
  - 1f979c36d507 — this branch's 0019 rearm threshold -> 0022 evidence
    document versioning chain (P3 hysteresis/debounce/calc-metrics, P4
    EVID-001 E0-E2)

Neither side touches the same tables, so this merge migration is a
no-op — it exists solely to collapse the two heads back into a single
linear chain, same pattern as 0013_merge_heads/0019_merge_heads before it.

Revision ID: 0023_merge_heads
Revises: 0019_merge_heads, 1f979c36d507
Create Date: 2026-09-18
"""

from collections.abc import Sequence

revision: str = "0023_merge_heads"
down_revision: str | Sequence[str] | None = ("0019_merge_heads", "1f979c36d507")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
