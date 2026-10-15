CREATE TABLE IF NOT EXISTS
                        support_tickets (
                            id INTEGER
                                PRIMARY KEY
                                AUTOINCREMENT,

                            public_id TEXT
                                UNIQUE,

                            owner_user_id INTEGER
                                NOT NULL,

                            account_id INTEGER
                                NOT NULL,

                            first_name TEXT
                                NOT NULL,

                            last_name TEXT
                                NOT NULL,

                            email TEXT
                                NOT NULL,

                            category TEXT
                                NOT NULL,

                            subject TEXT
                                NOT NULL,

                            description TEXT
                                NOT NULL,

                            priority TEXT
                                NOT NULL
                                DEFAULT 'normal'
                                CHECK(
                                    priority IN (
                                        'low',
                                        'normal',
                                        'high',
                                        'urgent'
                                    )
                                ),

                            status TEXT
                                NOT NULL
                                DEFAULT 'open'
                                CHECK(
                                    status IN (
                                        'open',
                                        'in_progress',
                                        'resolved',
                                        'closed'
                                    )
                                ),

                            organization_id INTEGER,

                            company_id INTEGER,

                            page_path TEXT
                                NOT NULL
                                DEFAULT '',

                            app_version TEXT
                                NOT NULL
                                DEFAULT '',

                            browser TEXT
                                NOT NULL
                                DEFAULT '',

                            created_at TEXT
                                NOT NULL,

                            updated_at TEXT
                                NOT NULL
                        );

                        CREATE INDEX IF NOT EXISTS
                        idx_support_owner
                        ON support_tickets(
                            owner_user_id,
                            id DESC
                        );

                        CREATE INDEX IF NOT EXISTS
                        idx_support_status
                        ON support_tickets(
                            status,
                            id DESC
                        );


            CREATE TABLE IF NOT EXISTS
            support_ticket_messages (
                id INTEGER
                    PRIMARY KEY
                    AUTOINCREMENT,

                ticket_id INTEGER
                    NOT NULL
                    REFERENCES support_tickets(id)
                    ON DELETE CASCADE,

                author_type TEXT
                    NOT NULL
                    CHECK(
                        author_type IN (
                            'user',
                            'support'
                        )
                    ),

                author_account_id INTEGER,

                author_email TEXT
                    NOT NULL
                    DEFAULT '',

                body TEXT
                    NOT NULL,

                created_at TEXT
                    NOT NULL
            )
            ;

            CREATE INDEX IF NOT EXISTS
            idx_support_messages_ticket
            ON support_ticket_messages(
                ticket_id,
                id ASC
            )
            ;
