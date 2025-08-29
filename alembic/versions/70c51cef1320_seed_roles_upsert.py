"""seed roles (upsert)

Revision ID: 70c51cef1320
Revises: 2b3e44fb958d
Create Date: 2025-08-29 02:09:58.655488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = '70c51cef1320'
down_revision: Union[str, Sequence[str], None] = '2b3e44fb958d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String(64)),
    )
    bind = op.get_bind()
    stmt = pg_insert(roles).values([{"name": "user"}, {"name": "admin"}])
    stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
    bind.execute(stmt)

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM roles WHERE name IN ('user','admin');")
