CREATE TABLE IF NOT EXISTS rag_chunks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL,
                            pdf_sha256 TEXT NOT NULL,
                            chunk_index INTEGER NOT NULL,
                            page_number INTEGER NOT NULL,
                            chunk_text TEXT NOT NULL,
                            vector_blob BLOB NOT NULL,
                            created_at TEXT NOT NULL,
                            UNIQUE(owner_user_id, pdf_sha256, chunk_index)
                        );
                        CREATE INDEX IF NOT EXISTS idx_rag_document
                        ON rag_chunks(owner_user_id, pdf_sha256, chunk_index);
