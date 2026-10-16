"""init

Revision ID: 001
Revises: 
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建组织架构表
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('org_code', sa.String(50), nullable=False),
        sa.Column('org_name', sa.String(100), nullable=False),
        sa.Column('org_type', sa.String(50), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_code')
    )
    op.create_index('idx_org_code', 'organizations', ['org_code'])
    op.create_index('idx_parent_id', 'organizations', ['parent_id'])

    # 创建用户表
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('real_name', sa.String(50), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(100), nullable=True),
        sa.Column('avatar', sa.String(500), nullable=True),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('active', 'inactive', 'locked', 'deleted'), nullable=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=True),
        sa.Column('last_login_time', sa.DateTime(), nullable=True),
        sa.Column('last_login_ip', sa.String(50), nullable=True),
        sa.Column('login_count', sa.Integer(), nullable=True),
        sa.Column('failed_login_count', sa.Integer(), nullable=True),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('phone'),
        sa.UniqueConstraint('email')
    )
    op.create_index('idx_username', 'users', ['username'])
    op.create_index('idx_phone', 'users', ['phone'])
    op.create_index('idx_email', 'users', ['email'])
    op.create_index('idx_organization_id', 'users', ['organization_id'])


def downgrade() -> None:
    op.drop_table('users')
    op.drop_table('organizations')
