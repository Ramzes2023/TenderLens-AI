CREATE TABLE IF NOT EXISTS auth_accounts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                            password_hash TEXT NOT NULL,
                            owner_user_id INTEGER UNIQUE,
                            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_accounts_owner ON auth_accounts(owner_user_id);
                        CREATE TABLE IF NOT EXISTS auth_sessions (
                            token_hash TEXT PRIMARY KEY,
                            account_id INTEGER NOT NULL,
                            expires_at TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            last_seen_at TEXT NOT NULL,
                            FOREIGN KEY(account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_sessions_account ON auth_sessions(account_id, expires_at);
                        CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);

                        CREATE TABLE IF NOT EXISTS auth_telegram_links (
                            token_hash TEXT PRIMARY KEY,
                            account_id INTEGER NOT NULL,
                            expires_at TEXT NOT NULL,
                            consumed_at TEXT,
                            created_at TEXT NOT NULL,
                            FOREIGN KEY(account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_telegram_links_account
                        ON auth_telegram_links(account_id, expires_at);

                        CREATE TABLE IF NOT EXISTS auth_password_resets (
                            token_hash TEXT PRIMARY KEY,
                            account_id INTEGER NOT NULL,
                            expires_at TEXT NOT NULL,
                            consumed_at TEXT,
                            created_at TEXT NOT NULL,
                            FOREIGN KEY(account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_password_resets_account
                        ON auth_password_resets(account_id, created_at);
                        CREATE INDEX IF NOT EXISTS idx_auth_password_resets_expires
                        ON auth_password_resets(expires_at);

                        CREATE TABLE IF NOT EXISTS auth_email_verifications (
                            token_hash TEXT PRIMARY KEY,
                            account_id INTEGER NOT NULL,
                            expires_at TEXT NOT NULL,
                            consumed_at TEXT,
                            created_at TEXT NOT NULL,
                            FOREIGN KEY(account_id)
                                REFERENCES auth_accounts(id)
                                ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_email_verifications_account
                        ON auth_email_verifications(
                            account_id,
                            expires_at
                        );
