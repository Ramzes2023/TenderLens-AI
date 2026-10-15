CREATE TABLE IF NOT EXISTS company_workspaces (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL,
                            name TEXT NOT NULL,
                            profile_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(owner_user_id, name)
                        );

                        CREATE INDEX IF NOT EXISTS idx_company_owner
                        ON company_workspaces(owner_user_id, updated_at DESC);

                        CREATE TABLE IF NOT EXISTS company_active (
                            owner_user_id INTEGER PRIMARY KEY,
                            company_id INTEGER NOT NULL,
                            updated_at TEXT NOT NULL,
                            FOREIGN KEY(company_id) REFERENCES company_workspaces(id) ON DELETE CASCADE
                        );
