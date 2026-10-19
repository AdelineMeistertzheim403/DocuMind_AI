"""Initial document schema, deliberately frozen independently of ORM models."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_name", sa.String(64), nullable=False, unique=True),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_table("document_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number"))
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_table("document_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Uuid(), sa.ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index"))
    for column in ("document_id", "page_id"):
        op.create_index(f"ix_document_chunks_{column}", "document_chunks", [column])
    op.create_table("analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("parameters", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("result", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_analyses_document_id", "analyses", ["document_id"])


def downgrade():
    for table in ("analyses", "document_chunks", "document_pages", "documents"):
        op.drop_table(table)
