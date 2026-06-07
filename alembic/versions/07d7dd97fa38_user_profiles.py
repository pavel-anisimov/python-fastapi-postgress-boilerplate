"""user_profiles

Revision ID: 07d7dd97fa38
Revises: 70c51cef1320
Create Date: 2026-06-07 11:47:03.264563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07d7dd97fa38'
down_revision: Union[str, Sequence[str], None] = '70c51cef1320'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=True),
    sa.Column('first_name', sa.String(length=255), nullable=True),
    sa.Column('last_name', sa.String(length=255), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('avatar_url', sa.String(length=2048), nullable=True),
    sa.Column('phone_number', sa.String(length=32), nullable=True),
    sa.Column('date_of_birth', sa.Date(), nullable=True),
    sa.Column('location_city', sa.String(length=255), nullable=True),
    sa.Column('location_state', sa.String(length=255), nullable=True),
    sa.Column('location_country', sa.String(length=255), nullable=True),
    sa.Column('location_zip', sa.String(length=32), nullable=True),
    sa.Column('language', sa.String(length=16), server_default='en', nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=True),
    sa.Column('profile_completed', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_profiles_user_id'), 'user_profiles', ['user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_profiles_user_id'), table_name='user_profiles')
    op.drop_table('user_profiles')
