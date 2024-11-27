"""initial schema

Revision ID: initial_schema
Revises: 
Create Date: 2024-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String()),
        sa.Column('raw_data', sa.JSON()),
        sa.PrimaryKeyConstraint('id')
    )

    # Create facilities table
    op.create_table(
        'facilities',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String()),
        sa.Column('tenant_id', sa.String()),
        sa.Column('raw_data', sa.JSON()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Create facility_scenarios table
    op.create_table(
        'facility_scenarios',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String()),
        sa.Column('tenant_id', sa.String()),
        sa.Column('facility_id', sa.String()),
        sa.Column('raw_data', sa.JSON()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['facility_id'], ['facilities.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Create work_orders table
    op.create_table(
        'work_orders',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('external_id', sa.String()),
        sa.Column('tenant_id', sa.String()),
        sa.Column('facility_scenario_id', sa.String()),
        sa.Column('raw_data', sa.JSON()),
        sa.Column('status', sa.String(), nullable=False, server_default='UNPROCESSED'),
        sa.Column('review_notes', sa.String(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['facility_scenario_id'], ['facility_scenarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'facility_scenario_id', 'external_id')
    )

    # Create work_order_matches table
    op.create_table(
        'work_order_matches',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('work_order_id', sa.String()),
        sa.Column('assessment_id', sa.String()),
        sa.Column('asset_client_id', sa.String()),
        sa.Column('asset_name', sa.String()),
        sa.Column('component', sa.String()),
        sa.Column('confidence_score', sa.Float()),
        sa.Column('matching_reasoning', sa.String()),
        sa.Column('is_repair', sa.Boolean()),
        sa.Column('repair_reasoning', sa.String()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id']),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('work_order_matches')
    op.drop_table('work_orders')
    op.drop_table('facility_scenarios')
    op.drop_table('facilities')
    op.drop_table('tenants')