CREATE TABLE IF NOT EXISTS schema_meta (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS tenders (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL,
                            chat_id INTEGER NOT NULL,
                            pdf_sha256 TEXT NOT NULL,
                            source_filename TEXT NOT NULL,
                            pages INTEGER,
                            characters INTEGER NOT NULL,
                            analysis_json TEXT NOT NULL,
                            scoring_json TEXT,
                            analysis_truncated INTEGER NOT NULL DEFAULT 0 CHECK (analysis_truncated IN (0,1)),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(owner_user_id, pdf_sha256)
                        );

                        CREATE INDEX IF NOT EXISTS idx_tenders_owner_created
                        ON tenders(owner_user_id, created_at DESC);

                        CREATE TABLE IF NOT EXISTS saved_opportunities (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            organization_id INTEGER NOT NULL,
                            company_id INTEGER NOT NULL,
                            source TEXT NOT NULL,
                            external_id TEXT NOT NULL,
                            snapshot_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(
                                organization_id,
                                company_id,
                                source,
                                external_id
                            )
                        );

                        CREATE INDEX IF NOT EXISTS idx_saved_opportunities_scope
                        ON saved_opportunities(
                            organization_id,
                            company_id,
                            updated_at DESC,
                            id DESC
                        );

                        CREATE TABLE IF NOT EXISTS discovery_search_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            organization_id INTEGER NOT NULL,
                            company_id INTEGER NOT NULL,
                            created_by_account_id INTEGER NOT NULL,
                            result_count INTEGER NOT NULL
                                CHECK(result_count >= 0),
                            scored_count INTEGER NOT NULL
                                CHECK(scored_count >= 0),
                            attempted_sources_json TEXT NOT NULL,
                            successful_sources_json TEXT NOT NULL,
                            failed_sources_json TEXT NOT NULL,
                            partial_failure INTEGER NOT NULL
                                CHECK(partial_failure IN (0,1)),
                            total_failure INTEGER NOT NULL
                                CHECK(total_failure IN (0,1)),
                            snapshot_json TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        );

                        CREATE INDEX IF NOT EXISTS
                        idx_discovery_search_history_scope
                        ON discovery_search_history(
                            organization_id,
                            company_id,
                            created_at DESC,
                            id DESC
                        );
