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


def upgrade():
    # 1) In case the roles table has not been created yet (for example, create_all has not been called before)
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'roles' AND table_schema = 'public'
      ) THEN
        CREATE TABLE public.roles (
          id   SERIAL PRIMARY KEY,
          name VARCHAR(64) NOT NULL
        );
      END IF;
    END$$;
    """)

    # 2) Guarantee the uniqueness of name (needed for ON CONFLICT)
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conname = 'uq_roles_name'
      ) THEN
        ALTER TABLE public.roles
        ADD CONSTRAINT uq_roles_name UNIQUE (name);
      END IF;
    END$$;
    """)

    #3) Seeds - now you can safely carry a unique key.
    op.execute("""
    INSERT INTO public.roles (name) VALUES
      ('user'),
      ('admin')
    ON CONFLICT ON CONSTRAINT uq_roles_name DO NOTHING;
    """)

def downgrade():
    # Roll back seeds (optional, but correct)
    op.execute("DELETE FROM public.roles WHERE name IN ('user','admin');")

    # Remove the unique restriction if you need to roll back cleanly
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_roles_name'
      ) THEN
        ALTER TABLE public.roles DROP CONSTRAINT uq_roles_name;
      END IF;
    END$$;
    """)