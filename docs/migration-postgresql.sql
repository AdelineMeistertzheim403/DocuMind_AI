BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE documents (
    id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    storage_name VARCHAR(64) NOT NULL, 
    media_type VARCHAR(32) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (storage_name)
);

CREATE INDEX ix_documents_owner_id ON documents (owner_id);

CREATE TABLE document_pages (
    id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    page_number INTEGER NOT NULL, 
    text TEXT NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (document_id, page_number), 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_pages_document_id ON document_pages (document_id);

CREATE TABLE document_chunks (
    id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    page_id UUID NOT NULL, 
    chunk_index INTEGER NOT NULL, 
    start_char INTEGER NOT NULL, 
    end_char INTEGER NOT NULL, 
    text TEXT NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (document_id, chunk_index), 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    FOREIGN KEY(page_id) REFERENCES document_pages (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id);

CREATE INDEX ix_document_chunks_page_id ON document_chunks (page_id);

CREATE TABLE analyses (
    id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    engine_version VARCHAR(32) NOT NULL, 
    parameters JSONB NOT NULL, 
    result JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX ix_analyses_document_id ON analyses (document_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

