"""Bootstrap RunWise sync tables and add updated_at for incremental sync."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261003_01"
down_revision = None
branch_labels = None
depends_on = None


def _create_missing_tables(bind):
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=False)

    if "activities" not in tables:
        op.create_table(
            "activities",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("external_id", sa.String(255), nullable=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("race_id", sa.String(128), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=False),
            sa.Column("distance_meters", sa.Float(), nullable=False),
            sa.Column("avg_heart_rate", sa.Float(), nullable=True),
            sa.Column("elevation_gain_meters", sa.Float(), nullable=True),
            sa.Column("avg_pace_seconds_per_km", sa.Float(), nullable=True),
            sa.UniqueConstraint("user_id", "source", "external_id", name="uq_activity_external"),
        )
        op.create_index("ix_activities_user_id", "activities", ["user_id"], unique=False)
        op.create_index("ix_activities_started_at", "activities", ["started_at"], unique=False)

    if "goals" not in tables:
        op.create_table(
            "goals",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("target_value", sa.Float(), nullable=False),
            sa.Column("current_value", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(32), nullable=False),
            sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_goals_user_id", "goals", ["user_id"], unique=False)

    if "races" not in tables:
        op.create_table(
            "races",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("provider", sa.String(64), nullable=False),
            sa.Column("external_id", sa.String(255), nullable=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("distance_meters", sa.Float(), nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("registration_status", sa.String(64), nullable=False),
            sa.UniqueConstraint("user_id", "provider", "external_id", name="uq_race_external"),
        )
        op.create_index("ix_races_user_id", "races", ["user_id"], unique=False)
        op.create_index("ix_races_date", "races", ["date"], unique=False)

    if "planned_workouts" not in tables:
        op.create_table(
            "planned_workouts",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("type", sa.String(32), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.String(2000), nullable=False),
            sa.Column("target_distance_meters", sa.Float(), nullable=True),
            sa.Column("target_duration_seconds", sa.Integer(), nullable=True),
            sa.Column("target_pace_min_seconds_per_km", sa.Float(), nullable=True),
            sa.Column("target_pace_max_seconds_per_km", sa.Float(), nullable=True),
            sa.Column("completed", sa.Boolean(), nullable=False),
            sa.Column("skipped", sa.Boolean(), nullable=False),
            sa.Column("generated_reason", sa.String(1000), nullable=True),
        )
        op.create_index("ix_planned_workouts_user_id", "planned_workouts", ["user_id"], unique=False)
        op.create_index("ix_planned_workouts_date", "planned_workouts", ["date"], unique=False)


def upgrade():
    bind = op.get_bind()
    _create_missing_tables(bind)
    inspector = inspect(bind)
    for table in ("activities", "goals", "races", "planned_workouts"):
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "updated_at" not in cols:
            op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
            op.execute(sa.text(f"UPDATE {table} SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
            op.alter_column(table, "updated_at", nullable=False)
        indexes = {i["name"] for i in inspect(bind).get_indexes(table)}
        if f"ix_{table}_updated_at" not in indexes:
            op.create_index(f"ix_{table}_updated_at", table, ["updated_at"])


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("activities", "goals", "races", "planned_workouts"):
        if table in inspector.get_table_names():
            indexes = {i["name"] for i in inspect(bind).get_indexes(table)}
            if f"ix_{table}_updated_at" in indexes:
                op.drop_index(f"ix_{table}_updated_at", table_name=table)
            if "updated_at" in {c["name"] for c in inspect(bind).get_columns(table)}:
                op.drop_column(table, "updated_at")
