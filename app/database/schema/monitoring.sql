CREATE TABLE IF NOT EXISTS monitor_subscriptions (
                            owner_user_id INTEGER PRIMARY KEY,
                            chat_id INTEGER NOT NULL,
                            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS monitor_seen (
                            owner_user_id INTEGER NOT NULL,
                            source TEXT NOT NULL,
                            external_id TEXT NOT NULL,
                            first_seen_at TEXT NOT NULL,
                            PRIMARY KEY(owner_user_id, source, external_id)
                        );

                        CREATE INDEX IF NOT EXISTS idx_monitor_subscriptions_enabled
                        ON monitor_subscriptions(enabled, updated_at DESC);
