CREATE TABLE IF NOT EXISTS app_data_imports (
    source_fingerprint TEXT PRIMARY KEY,
    completed_at TEXT NOT NULL
);
