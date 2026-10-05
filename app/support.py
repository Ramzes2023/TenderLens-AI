"""Persistent support tickets for VALYQON AI."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class SupportRepositoryError(RuntimeError):
    pass


class SupportTicketNotFound(SupportRepositoryError):
    pass


@dataclass(frozen=True)
class SupportTicket:
    id: int
    public_id: str
    owner_user_id: int
    account_id: int
    first_name: str
    last_name: str
    email: str
    category: str
    subject: str
    description: str
    priority: str
    status: str
    organization_id: int | None
    company_id: int | None
    page_path: str
    app_version: str
    browser: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SupportMessage:
    id: int
    ticket_id: int
    author_type: str
    author_account_id: int | None
    author_email: str
    body: str
    created_at: str


class SupportRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=10,
        )

        conn.row_factory = sqlite3.Row

        conn.execute(
            "PRAGMA foreign_keys=ON"
        )

        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

    @staticmethod
    def _ticket(
        row: sqlite3.Row,
    ) -> SupportTicket:

        return SupportTicket(
            id=int(row["id"]),
            public_id=str(
                row["public_id"]
            ),
            owner_user_id=int(
                row["owner_user_id"]
            ),
            account_id=int(
                row["account_id"]
            ),
            first_name=str(
                row["first_name"]
            ),
            last_name=str(
                row["last_name"]
            ),
            email=str(
                row["email"]
            ),
            category=str(
                row["category"]
            ),
            subject=str(
                row["subject"]
            ),
            description=str(
                row["description"]
            ),
            priority=str(
                row["priority"]
            ),
            status=str(
                row["status"]
            ),
            organization_id=(
                int(
                    row[
                        "organization_id"
                    ]
                )
                if row[
                    "organization_id"
                ] is not None
                else None
            ),
            company_id=(
                int(
                    row[
                        "company_id"
                    ]
                )
                if row[
                    "company_id"
                ] is not None
                else None
            ),
            page_path=str(
                row["page_path"]
                or ""
            ),
            app_version=str(
                row["app_version"]
                or ""
            ),
            browser=str(
                row["browser"]
                or ""
            ),
            created_at=str(
                row["created_at"]
            ),
            updated_at=str(
                row["updated_at"]
            ),
        )

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with closing(
                self._connect()
            ) as conn:

                with conn:
                    conn.executescript(
                        """
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
                        """
                    )

        except (
            OSError,
            sqlite3.Error,
        ):
            raise SupportRepositoryError(
                "Could not initialize "
                "support storage."
            ) from None

    def create_ticket(
        self,
        *,
        owner_user_id: int,
        account_id: int,
        first_name: str,
        last_name: str,
        email: str,
        category: str,
        subject: str,
        description: str,
        priority: str,
        organization_id: int | None,
        company_id: int | None,
        page_path: str,
        app_version: str,
        browser: str,
    ) -> SupportTicket:

        now = self._now()

        try:
            with closing(
                self._connect()
            ) as conn:

                with conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO
                        support_tickets(
                            public_id,
                            owner_user_id,
                            account_id,
                            first_name,
                            last_name,
                            email,
                            category,
                            subject,
                            description,
                            priority,
                            status,
                            organization_id,
                            company_id,
                            page_path,
                            app_version,
                            browser,
                            created_at,
                            updated_at
                        )
                        VALUES(
                            NULL,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            'open',
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?
                        )
                        """,
                        (
                            int(
                                owner_user_id
                            ),
                            int(
                                account_id
                            ),
                            first_name,
                            last_name,
                            email,
                            category,
                            subject,
                            description,
                            priority,
                            organization_id,
                            company_id,
                            page_path,
                            app_version,
                            browser,
                            now,
                            now,
                        ),
                    )

                    row_id = int(
                        cursor.lastrowid
                    )

                    public_id = (
                        f"VAL-"
                        f"{now[:4]}-"
                        f"{row_id:06d}"
                    )

                    conn.execute(
                        """
                        UPDATE support_tickets
                        SET public_id=?
                        WHERE id=?
                        """,
                        (
                            public_id,
                            row_id,
                        ),
                    )

                    row = conn.execute(
                        """
                        SELECT *
                        FROM support_tickets
                        WHERE id=?
                        """,
                        (
                            row_id,
                        ),
                    ).fetchone()

            if row is None:
                raise SupportRepositoryError(
                    "Could not create "
                    "support ticket."
                )

            return self._ticket(
                row
            )

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not create "
                "support ticket."
            ) from None

    def list_tickets(
        self,
        owner_user_id: int,
        limit: int = 50,
    ) -> list[SupportTicket]:

        safe_limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        try:
            with closing(
                self._connect()
            ) as conn:

                rows = conn.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE owner_user_id=?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (
                        int(
                            owner_user_id
                        ),
                        safe_limit,
                    ),
                ).fetchall()

            return [
                self._ticket(row)
                for row in rows
            ]

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not load "
                "support tickets."
            ) from None

    def get_ticket(
        self,
        owner_user_id: int,
        public_id: str,
    ) -> SupportTicket:

        try:
            with closing(
                self._connect()
            ) as conn:

                row = conn.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE owner_user_id=?
                      AND public_id=?
                    """,
                    (
                        int(
                            owner_user_id
                        ),
                        public_id,
                    ),
                ).fetchone()

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not load "
                "support ticket."
            ) from None

        if row is None:
            raise SupportTicketNotFound(
                "Support ticket not found."
            )

        return self._ticket(
            row
        )


    @staticmethod
    def _message(
        row: sqlite3.Row,
    ) -> SupportMessage:

        return SupportMessage(
            id=int(row["id"]),
            ticket_id=int(row["ticket_id"]),
            author_type=str(
                row["author_type"]
            ),
            author_account_id=(
                int(row["author_account_id"])
                if row["author_account_id"]
                is not None
                else None
            ),
            author_email=str(
                row["author_email"]
                or ""
            ),
            body=str(row["body"]),
            created_at=str(
                row["created_at"]
            ),
        )

    @staticmethod
    def _ensure_messages_schema(
        conn: sqlite3.Connection,
    ) -> None:

        conn.execute(
            """
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
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_support_messages_ticket
            ON support_ticket_messages(
                ticket_id,
                id ASC
            )
            """
        )

    def list_all_tickets_for_support(
        self,
        limit: int = 50,
        status: str | None = None,
    ) -> list[SupportTicket]:

        safe_limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        allowed_statuses = {
            "open",
            "in_progress",
            "resolved",
            "closed",
        }

        if (
            status is not None
            and status not in allowed_statuses
        ):
            raise SupportRepositoryError(
                "Invalid support ticket status."
            )

        try:
            with closing(
                self._connect()
            ) as conn:

                if status is None:
                    rows = conn.execute(
                        """
                        SELECT *
                        FROM support_tickets
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (
                            safe_limit,
                        ),
                    ).fetchall()

                else:
                    rows = conn.execute(
                        """
                        SELECT *
                        FROM support_tickets
                        WHERE status=?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (
                            status,
                            safe_limit,
                        ),
                    ).fetchall()

            return [
                self._ticket(row)
                for row in rows
            ]

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not load support tickets."
            ) from None

    def get_ticket_for_support(
        self,
        public_id: str,
    ) -> SupportTicket:

        try:
            with closing(
                self._connect()
            ) as conn:

                row = conn.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE public_id=?
                    """,
                    (
                        public_id,
                    ),
                ).fetchone()

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not load support ticket."
            ) from None

        if row is None:
            raise SupportTicketNotFound(
                "Support ticket not found."
            )

        return self._ticket(row)

    def list_ticket_messages(
        self,
        owner_user_id: int,
        public_id: str,
    ) -> list[SupportMessage]:

        try:
            with closing(
                self._connect()
            ) as conn:

                self._ensure_messages_schema(
                    conn
                )

                ticket = conn.execute(
                    """
                    SELECT id
                    FROM support_tickets
                    WHERE owner_user_id=?
                      AND public_id=?
                    """,
                    (
                        int(owner_user_id),
                        public_id,
                    ),
                ).fetchone()

                if ticket is None:
                    raise SupportTicketNotFound(
                        "Support ticket not found."
                    )

                rows = conn.execute(
                    """
                    SELECT *
                    FROM support_ticket_messages
                    WHERE ticket_id=?
                    ORDER BY id ASC
                    """,
                    (
                        int(ticket["id"]),
                    ),
                ).fetchall()

            return [
                self._message(row)
                for row in rows
            ]

        except SupportTicketNotFound:
            raise

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not load support messages."
            ) from None

    def list_ticket_messages_for_support(
        self,
        public_id: str,
    ) -> list[SupportMessage]:

        ticket = self.get_ticket_for_support(
            public_id
        )

        try:
            with closing(
                self._connect()
            ) as conn:

                self._ensure_messages_schema(
                    conn
                )

                rows = conn.execute(
                    """
                    SELECT *
                    FROM support_ticket_messages
                    WHERE ticket_id=?
                    ORDER BY id ASC
                    """,
                    (
                        ticket.id,
                    ),
                ).fetchall()

            return [
                self._message(row)
                for row in rows
            ]

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not load support messages."
            ) from None

    def add_ticket_message(
        self,
        *,
        owner_user_id: int,
        public_id: str,
        account_id: int,
        email: str,
        body: str,
    ) -> SupportMessage:

        clean_body = body.strip()

        if not clean_body:
            raise SupportRepositoryError(
                "Support message is empty."
            )

        now = self._now()

        try:
            with closing(
                self._connect()
            ) as conn:

                with conn:
                    self._ensure_messages_schema(
                        conn
                    )

                    ticket = conn.execute(
                        """
                        SELECT id, status
                        FROM support_tickets
                        WHERE owner_user_id=?
                          AND public_id=?
                        """,
                        (
                            int(owner_user_id),
                            public_id,
                        ),
                    ).fetchone()

                    if ticket is None:
                        raise SupportTicketNotFound(
                            "Support ticket not found."
                        )

                    cursor = conn.execute(
                        """
                        INSERT INTO
                        support_ticket_messages(
                            ticket_id,
                            author_type,
                            author_account_id,
                            author_email,
                            body,
                            created_at
                        )
                        VALUES(
                            ?,
                            'user',
                            ?,
                            ?,
                            ?,
                            ?
                        )
                        """,
                        (
                            int(ticket["id"]),
                            int(account_id),
                            email.strip().lower(),
                            clean_body,
                            now,
                        ),
                    )

                    new_status = (
                        "open"
                        if str(ticket["status"])
                        in {
                            "resolved",
                            "closed",
                        }
                        else str(ticket["status"])
                    )

                    conn.execute(
                        """
                        UPDATE support_tickets
                        SET status=?,
                            updated_at=?
                        WHERE id=?
                        """,
                        (
                            new_status,
                            now,
                            int(ticket["id"]),
                        ),
                    )

                    row = conn.execute(
                        """
                        SELECT *
                        FROM support_ticket_messages
                        WHERE id=?
                        """,
                        (
                            int(cursor.lastrowid),
                        ),
                    ).fetchone()

            if row is None:
                raise SupportRepositoryError(
                    "Could not save support message."
                )

            return self._message(row)

        except SupportTicketNotFound:
            raise

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not save support message."
            ) from None

    def add_support_message(
        self,
        *,
        public_id: str,
        account_id: int,
        email: str,
        body: str,
    ) -> SupportMessage:

        clean_body = body.strip()

        if not clean_body:
            raise SupportRepositoryError(
                "Support message is empty."
            )

        now = self._now()

        try:
            with closing(
                self._connect()
            ) as conn:

                with conn:
                    self._ensure_messages_schema(
                        conn
                    )

                    ticket = conn.execute(
                        """
                        SELECT id
                        FROM support_tickets
                        WHERE public_id=?
                        """,
                        (
                            public_id,
                        ),
                    ).fetchone()

                    if ticket is None:
                        raise SupportTicketNotFound(
                            "Support ticket not found."
                        )

                    cursor = conn.execute(
                        """
                        INSERT INTO
                        support_ticket_messages(
                            ticket_id,
                            author_type,
                            author_account_id,
                            author_email,
                            body,
                            created_at
                        )
                        VALUES(
                            ?,
                            'support',
                            ?,
                            ?,
                            ?,
                            ?
                        )
                        """,
                        (
                            int(ticket["id"]),
                            int(account_id),
                            email.strip().lower(),
                            clean_body,
                            now,
                        ),
                    )

                    conn.execute(
                        """
                        UPDATE support_tickets
                        SET updated_at=?
                        WHERE id=?
                        """,
                        (
                            now,
                            int(ticket["id"]),
                        ),
                    )

                    row = conn.execute(
                        """
                        SELECT *
                        FROM support_ticket_messages
                        WHERE id=?
                        """,
                        (
                            int(cursor.lastrowid),
                        ),
                    ).fetchone()

            if row is None:
                raise SupportRepositoryError(
                    "Could not save support reply."
                )

            return self._message(row)

        except SupportTicketNotFound:
            raise

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not save support reply."
            ) from None

    def update_ticket_status_for_support(
        self,
        public_id: str,
        status: str,
    ) -> SupportTicket:

        allowed_statuses = {
            "open",
            "in_progress",
            "resolved",
            "closed",
        }

        if status not in allowed_statuses:
            raise SupportRepositoryError(
                "Invalid support ticket status."
            )

        now = self._now()

        try:
            with closing(
                self._connect()
            ) as conn:

                with conn:
                    cursor = conn.execute(
                        """
                        UPDATE support_tickets
                        SET status=?,
                            updated_at=?
                        WHERE public_id=?
                        """,
                        (
                            status,
                            now,
                            public_id,
                        ),
                    )

                    if cursor.rowcount != 1:
                        raise SupportTicketNotFound(
                            "Support ticket not found."
                        )

                    row = conn.execute(
                        """
                        SELECT *
                        FROM support_tickets
                        WHERE public_id=?
                        """,
                        (
                            public_id,
                        ),
                    ).fetchone()

            if row is None:
                raise SupportTicketNotFound(
                    "Support ticket not found."
                )

            return self._ticket(row)

        except SupportTicketNotFound:
            raise

        except sqlite3.Error:
            raise SupportRepositoryError(
                "Could not update support ticket."
            ) from None
