"""0019 merge credentials-and-research head with the monitoring chain

Combines the two heads that branched off migration 0012
(a1f3c9b7e2d4, evidence_bundle research_message_id link):

  - 0013_merge_heads — this branch's own reconciliation of the Supabase
    credentials migration (0150dc1bec31) with 0012, done locally before this
    merge, from `git pull`ing main was available.
  - 38fa495cbdf5 — main's migrations 0013 (calculation_job_queue) through
    0018 (evaluator_heartbeat): job queue, monitoring rules/evaluations,
    alerts, delivery attempts, coverage, and the dead-man heartbeat.

Neither side touches a table or column the other does, so — same as
0013_merge_heads — this is a no-op that exists only to collapse two valid
heads back into one linear chain.

Revision ID: 0019_merge_heads
Revises: 0013_merge_heads, 38fa495cbdf5
Create Date: 2026-09-18
"""

from collections.abc import Sequence

revision: str = "0019_merge_heads"
down_revision: str | Sequence[str] | None = ("0013_merge_heads", "38fa495cbdf5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
