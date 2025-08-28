"""seed roles

Revision ID: 94736178f846
Revises: 
Create Date: 2025-08-28 02:02:35.772352

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94736178f846'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("INSERT INTO roles (name) VALUES ('user') ON CONFLICT (name) DO NOTHING;")
    op.execute("INSERT INTO roles (name) VALUES ('admin') ON CONFLICT (name) DO NOTHING;")

    """Upgrade schema."""
    #pass


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM roles WHERE name IN ('user','admin');")

    #pass
