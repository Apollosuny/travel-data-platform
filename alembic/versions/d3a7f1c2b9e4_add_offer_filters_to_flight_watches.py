"""add offer filters to app flight watches

Revision ID: d3a7f1c2b9e4
Revises: bca04441d6f4
Create Date: 2026-10-06 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d3a7f1c2b9e4"
down_revision: Union[str, Sequence[str], None] = "bca04441d6f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "flight_watches",
        sa.Column("departure_time_from", sa.Time(), nullable=True),
        schema="app",
    )
    op.add_column(
        "flight_watches",
        sa.Column("departure_time_to", sa.Time(), nullable=True),
        schema="app",
    )
    op.add_column(
        "flight_watches",
        sa.Column("max_stops", sa.SmallInteger(), nullable=True),
        schema="app",
    )
    op.create_check_constraint(
        "ck_flight_watches_departure_window_order",
        "flight_watches",
        "departure_time_from IS NULL OR departure_time_to IS NULL "
        "OR departure_time_from <= departure_time_to",
        schema="app",
    )
    op.create_check_constraint(
        "ck_flight_watches_max_stops_non_negative",
        "flight_watches",
        "max_stops IS NULL OR max_stops >= 0",
        schema="app",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_flight_watches_max_stops_non_negative", "flight_watches", schema="app")
    op.drop_constraint("ck_flight_watches_departure_window_order", "flight_watches", schema="app")
    op.drop_column("flight_watches", "max_stops", schema="app")
    op.drop_column("flight_watches", "departure_time_to", schema="app")
    op.drop_column("flight_watches", "departure_time_from", schema="app")
