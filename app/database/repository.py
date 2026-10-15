"""Backend-neutral persistence for processed tenders.

The MVP stores metadata and structured results only: no PDF bytes and no extracted full text.
Repository operations own a connection lease and can run via asyncio.to_thread().
"""
from __future__ import annotations

import sqlite3
from app.database.backend import database_for, StorageError, StorageIntegrityError
from app.database.analytics_read import bounded_read, preflight
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models.tender import TenderAnalysis
from app.scoring.models import ScoringResult
from app.tenancy import organization_owner_id

SCHEMA_VERSION = 1


class DatabaseError(RuntimeError):
    pass


class DatabaseAuthorizationError(DatabaseError):
    pass


@dataclass(frozen=True)
class StoredTender:
    id: int
    owner_user_id: int
    chat_id: int
    pdf_sha256: str
    source_filename: str
    pages: int | None
    characters: int
    analysis: TenderAnalysis
    scoring: ScoringResult | None
    analysis_truncated: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SavedOpportunity:
    id: int
    organization_id: int
    company_id: int
    source: str
    external_id: str
    snapshot_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DiscoverySearchHistory:
    id: int
    organization_id: int
    company_id: int
    created_by_account_id: int
    result_count: int
    scored_count: int
    attempted_sources_json: str
    successful_sources_json: str
    failed_sources_json: str
    partial_failure: bool
    total_failure: bool
    snapshot_json: str
    created_at: str


class TenderRepository:
    def __init__(self, path):
        self.database = database_for(path)
        self.path = self.database.settings.path

    def _connect(self):
        return self.database.connect()

    def initialize(self) -> None:
        try:
            self.database.migrate("tenders")
        except (OSError, sqlite3.Error, StorageError, ValueError):
            raise DatabaseError("Could not initialize tenders storage.") from None

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> StoredTender:
        try:
            analysis = TenderAnalysis.model_validate_json(row["analysis_json"])
            scoring = (
                ScoringResult.model_validate_json(row["scoring_json"])
                if row["scoring_json"]
                else None
            )
            return StoredTender(
                id=row["id"],
                owner_user_id=row["owner_user_id"],
                chat_id=row["chat_id"],
                pdf_sha256=row["pdf_sha256"],
                source_filename=row["source_filename"],
                pages=row["pages"],
                characters=row["characters"],
                analysis=analysis,
                scoring=scoring,
                analysis_truncated=bool(row["analysis_truncated"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except Exception:
            raise DatabaseError("Сохранённая запись тендера повреждена.") from None

    @staticmethod
    def _deserialize_discovery_search_history(
        row: sqlite3.Row,
    ) -> DiscoverySearchHistory:
        try:
            return DiscoverySearchHistory(
                id=int(row["id"]),
                organization_id=int(
                    row["organization_id"]
                ),
                company_id=int(
                    row["company_id"]
                ),
                created_by_account_id=int(
                    row["created_by_account_id"]
                ),
                result_count=int(
                    row["result_count"]
                ),
                scored_count=int(
                    row["scored_count"]
                ),
                attempted_sources_json=str(
                    row["attempted_sources_json"]
                ),
                successful_sources_json=str(
                    row["successful_sources_json"]
                ),
                failed_sources_json=str(
                    row["failed_sources_json"]
                ),
                partial_failure=bool(
                    row["partial_failure"]
                ),
                total_failure=bool(
                    row["total_failure"]
                ),
                snapshot_json=str(
                    row["snapshot_json"]
                ),
                created_at=str(
                    row["created_at"]
                ),
            )
        except Exception:
            raise DatabaseError(
                "Stored discovery history is corrupted."
            ) from None

    @staticmethod
    def _require_org_role(
        conn: sqlite3.Connection,
        account_id: int,
        organization_id: int,
        allowed_roles: set[str] | None = None,
    ) -> str:
        row = conn.execute(
            """SELECT role
               FROM organization_members
               WHERE organization_id=? AND account_id=?""",
            (
                int(organization_id),
                int(account_id),
            ),
        ).fetchone()

        if row is None:
            raise DatabaseAuthorizationError(
                "Organization tender access denied."
            )

        role = str(row["role"])

        if (
            allowed_roles is not None
            and role not in allowed_roles
        ):
            raise DatabaseAuthorizationError(
                "Organization tender access denied."
            )

        return role

    def find_by_hash_for_organization(
        self,
        account_id: int,
        organization_id: int,
        pdf_sha256: str,
    ) -> StoredTender | None:
        owner_user_id = organization_owner_id(
            organization_id
        )

        try:
            with closing(self._connect()) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                row = conn.execute(
                    """SELECT *
                       FROM tenders
                       WHERE owner_user_id=? AND pdf_sha256=?""",
                    (
                        owner_user_id,
                        pdf_sha256,
                    ),
                ).fetchone()

            return (
                self._deserialize(row)
                if row is not None
                else None
            )

        except DatabaseAuthorizationError:
            raise
        except (sqlite3.Error, StorageError):
            raise DatabaseError(
                "Could not read organization tender history."
            ) from None

    def find_by_id_for_organization(
        self,
        account_id: int,
        organization_id: int,
        tender_id: int,
    ) -> StoredTender | None:
        owner_user_id = organization_owner_id(
            organization_id
        )

        try:
            with closing(self._connect()) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                row = conn.execute(
                    """SELECT *
                       FROM tenders
                       WHERE owner_user_id=? AND id=?""",
                    (
                        owner_user_id,
                        int(tender_id),
                    ),
                ).fetchone()

            return (
                self._deserialize(row)
                if row is not None
                else None
            )

        except DatabaseAuthorizationError:
            raise
        except (sqlite3.Error, StorageError, ValueError, TypeError):
            raise DatabaseError(
                "Could not read organization tender history."
            ) from None

    def list_recent_for_organization(
        self,
        account_id: int,
        organization_id: int,
        limit: int = 10,
    ) -> list[StoredTender]:
        owner_user_id = organization_owner_id(
            organization_id
        )
        limit = max(
            1,
            min(int(limit), 20),
        )

        try:
            with closing(self._connect()) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                rows = conn.execute(
                    """SELECT *
                       FROM tenders
                       WHERE owner_user_id=?
                       ORDER BY updated_at DESC, id DESC
                       LIMIT ?""",
                    (
                        owner_user_id,
                        limit,
                    ),
                ).fetchall()

            return [
                self._deserialize(row)
                for row in rows
            ]

        except DatabaseAuthorizationError:
            raise
        except (sqlite3.Error, StorageError, ValueError, TypeError):
            raise DatabaseError(
                "Could not read organization tender history."
            ) from None

    def save_success_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        pdf_sha256: str,
        source_filename: str,
        pages: int | None,
        characters: int,
        analysis: TenderAnalysis,
        scoring: ScoringResult | None,
        analysis_truncated: bool,
    ) -> StoredTender:
        owner_user_id = organization_owner_id(
            organization_id
        )
        now = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        analysis_json = analysis.model_dump_json()
        scoring_json = (
            scoring.model_dump_json()
            if scoring is not None
            else None
        )

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {
                            "owner",
                            "admin",
                            "member",
                        },
                    )

                    conn.execute(
                        """INSERT INTO tenders(
                            owner_user_id,
                            chat_id,
                            pdf_sha256,
                            source_filename,
                            pages,
                            characters,
                            analysis_json,
                            scoring_json,
                            analysis_truncated,
                            created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(owner_user_id, pdf_sha256)
                        DO UPDATE SET
                            chat_id=excluded.chat_id,
                            source_filename=excluded.source_filename,
                            pages=excluded.pages,
                            characters=excluded.characters,
                            analysis_json=excluded.analysis_json,
                            scoring_json=excluded.scoring_json,
                            analysis_truncated=excluded.analysis_truncated,
                            updated_at=excluded.updated_at""",
                        (
                            owner_user_id,
                            owner_user_id,
                            pdf_sha256,
                            source_filename,
                            pages,
                            characters,
                            analysis_json,
                            scoring_json,
                            int(analysis_truncated),
                            now,
                            now,
                        ),
                    )

                    row = conn.execute(
                        """SELECT *
                           FROM tenders
                           WHERE owner_user_id=? AND pdf_sha256=?""",
                        (
                            owner_user_id,
                            pdf_sha256,
                        ),
                    ).fetchone()

            if row is None:
                raise DatabaseError(
                    "Could not save organization tender."
                )

            return self._deserialize(row)

        except DatabaseAuthorizationError:
            raise
        except (sqlite3.Error, StorageError):
            raise DatabaseError(
                "Could not save organization tender."
            ) from None

    @staticmethod
    def _deserialize_saved_opportunity(
        row: sqlite3.Row,
    ) -> SavedOpportunity:
        try:
            return SavedOpportunity(
                id=int(row["id"]),
                organization_id=int(
                    row["organization_id"]
                ),
                company_id=int(
                    row["company_id"]
                ),
                source=str(row["source"]),
                external_id=str(
                    row["external_id"]
                ),
                snapshot_json=str(
                    row["snapshot_json"]
                ),
                created_at=str(
                    row["created_at"]
                ),
                updated_at=str(
                    row["updated_at"]
                ),
            )
        except Exception:
            raise DatabaseError(
                "Saved opportunity record is corrupted."
            ) from None

    @staticmethod
    def _require_company_scope(
        conn: sqlite3.Connection,
        organization_id: int,
        company_id: int,
    ) -> None:
        row = conn.execute(
            """SELECT id
               FROM company_workspaces
               WHERE organization_id=?
                 AND id=?""",
            (
                int(organization_id),
                int(company_id),
            ),
        ).fetchone()

        if row is None:
            raise DatabaseAuthorizationError(
                "Company shortlist access denied."
            )

    def save_opportunity_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        company_id: int,
        source: str,
        external_id: str,
        snapshot_json: str,
    ) -> SavedOpportunity:
        clean_source = " ".join(
            str(source).split()
        )[:100]

        clean_external_id = " ".join(
            str(external_id).split()
        )[:500]

        if (
            not clean_source
            or not clean_external_id
        ):
            raise DatabaseError(
                "Saved opportunity identity is invalid."
            )

        if not str(snapshot_json).strip():
            raise DatabaseError(
                "Saved opportunity snapshot is empty."
            )

        now = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        try:
            with closing(
                self._connect()
            ) as conn:
                with conn:
                    conn.execute(
                        "BEGIN IMMEDIATE"
                    )

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {
                            "owner",
                            "admin",
                            "member",
                        },
                    )

                    self._require_company_scope(
                        conn,
                        organization_id,
                        company_id,
                    )

                    conn.execute(
                        """INSERT INTO saved_opportunities(
                            organization_id,
                            company_id,
                            source,
                            external_id,
                            snapshot_json,
                            created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(
                            organization_id,
                            company_id,
                            source,
                            external_id
                        )
                        DO UPDATE SET
                            snapshot_json=excluded.snapshot_json,
                            updated_at=excluded.updated_at""",
                        (
                            int(organization_id),
                            int(company_id),
                            clean_source,
                            clean_external_id,
                            str(snapshot_json),
                            now,
                            now,
                        ),
                    )

                    row = conn.execute(
                        """SELECT *
                           FROM saved_opportunities
                           WHERE organization_id=?
                             AND company_id=?
                             AND source=?
                             AND external_id=?""",
                        (
                            int(organization_id),
                            int(company_id),
                            clean_source,
                            clean_external_id,
                        ),
                    ).fetchone()

            if row is None:
                raise DatabaseError(
                    "Could not save opportunity."
                )

            return (
                self._deserialize_saved_opportunity(
                    row
                )
            )

        except DatabaseAuthorizationError:
            raise

        except DatabaseError:
            raise

        except (sqlite3.Error, StorageError):
            raise DatabaseError(
                "Could not save opportunity."
            ) from None

    def list_saved_opportunities_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
        limit: int = 100,
    ) -> list[SavedOpportunity]:
        safe_limit = max(
            1,
            min(
                int(limit),
                200,
            ),
        )

        try:
            with closing(
                self._connect()
            ) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                self._require_company_scope(
                    conn,
                    organization_id,
                    company_id,
                )

                rows = conn.execute(
                    """SELECT *
                       FROM saved_opportunities
                       WHERE organization_id=?
                         AND company_id=?
                       ORDER BY
                         updated_at DESC,
                         id DESC
                       LIMIT ?""",
                    (
                        int(organization_id),
                        int(company_id),
                        safe_limit,
                    ),
                ).fetchall()

            return [
                self._deserialize_saved_opportunity(
                    row
                )
                for row in rows
            ]

        except DatabaseAuthorizationError:
            raise

        except (
            sqlite3.Error,
            StorageError,
            ValueError,
            TypeError,
        ):
            raise DatabaseError(
                "Could not read saved opportunities."
            ) from None

    def delete_saved_opportunity_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        company_id: int,
        saved_id: int,
    ) -> bool:
        try:
            with closing(
                self._connect()
            ) as conn:
                with conn:
                    conn.execute(
                        "BEGIN IMMEDIATE"
                    )

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {
                            "owner",
                            "admin",
                            "member",
                        },
                    )

                    self._require_company_scope(
                        conn,
                        organization_id,
                        company_id,
                    )

                    cursor = conn.execute(
                        """DELETE FROM saved_opportunities
                           WHERE id=?
                             AND organization_id=?
                             AND company_id=?""",
                        (
                            int(saved_id),
                            int(organization_id),
                            int(company_id),
                        ),
                    )

                    removed = (
                        cursor.rowcount == 1
                    )

            return removed

        except DatabaseAuthorizationError:
            raise

        except (
            sqlite3.Error,
            StorageError,
            ValueError,
            TypeError,
        ):
            raise DatabaseError(
                "Could not remove saved opportunity."
            ) from None

    def record_discovery_search_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        company_id: int,
        result_count: int,
        scored_count: int,
        attempted_sources_json: str,
        successful_sources_json: str,
        failed_sources_json: str,
        partial_failure: bool,
        total_failure: bool,
        snapshot_json: str,
    ) -> DiscoverySearchHistory:
        safe_result_count = int(
            result_count
        )

        safe_scored_count = int(
            scored_count
        )

        if (
            safe_result_count < 0
            or safe_scored_count < 0
            or safe_scored_count
            > safe_result_count
        ):
            raise DatabaseError(
                "Discovery history counts are invalid."
            )

        required_json = (
            attempted_sources_json,
            successful_sources_json,
            failed_sources_json,
            snapshot_json,
        )

        if any(
            not str(value).strip()
            for value in required_json
        ):
            raise DatabaseError(
                "Discovery history snapshot is empty."
            )

        now = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        try:
            with closing(
                self._connect()
            ) as conn:
                with conn:
                    conn.execute(
                        "BEGIN IMMEDIATE"
                    )

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                    )

                    self._require_company_scope(
                        conn,
                        organization_id,
                        company_id,
                    )

                    cursor = conn.execute(
                        """INSERT INTO discovery_search_history(
                            organization_id,
                            company_id,
                            created_by_account_id,
                            result_count,
                            scored_count,
                            attempted_sources_json,
                            successful_sources_json,
                            failed_sources_json,
                            partial_failure,
                            total_failure,
                            snapshot_json,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            int(organization_id),
                            int(company_id),
                            int(account_id),
                            safe_result_count,
                            safe_scored_count,
                            str(
                                attempted_sources_json
                            ),
                            str(
                                successful_sources_json
                            ),
                            str(
                                failed_sources_json
                            ),
                            int(
                                bool(
                                    partial_failure
                                )
                            ),
                            int(
                                bool(
                                    total_failure
                                )
                            ),
                            str(snapshot_json),
                            now,
                        ),
                    )

                    row = conn.execute(
                        """SELECT *
                           FROM discovery_search_history
                           WHERE id=?""",
                        (
                            int(
                                cursor.lastrowid
                            ),
                        ),
                    ).fetchone()

            if row is None:
                raise DatabaseError(
                    "Could not record discovery history."
                )

            return (
                self
                ._deserialize_discovery_search_history(
                    row
                )
            )

        except DatabaseAuthorizationError:
            raise

        except DatabaseError:
            raise

        except (
            sqlite3.Error,
            StorageError,
            ValueError,
            TypeError,
        ):
            raise DatabaseError(
                "Could not record discovery history."
            ) from None

    def list_discovery_search_history_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
        limit: int = 50,
    ) -> list[DiscoverySearchHistory]:
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
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                self._require_company_scope(
                    conn,
                    organization_id,
                    company_id,
                )

                rows = conn.execute(
                    """SELECT *
                       FROM discovery_search_history
                       WHERE organization_id=?
                         AND company_id=?
                       ORDER BY
                         created_at DESC,
                         id DESC
                       LIMIT ?""",
                    (
                        int(organization_id),
                        int(company_id),
                        safe_limit,
                    ),
                ).fetchall()

            return [
                self
                ._deserialize_discovery_search_history(
                    row
                )
                for row in rows
            ]

        except DatabaseAuthorizationError:
            raise

        except (
            sqlite3.Error,
            StorageError,
            ValueError,
            TypeError,
        ):
            raise DatabaseError(
                "Could not read discovery history."
            ) from None

    def get_discovery_search_history_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
        history_id: int,
    ) -> DiscoverySearchHistory | None:
        try:
            with closing(
                self._connect()
            ) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                self._require_company_scope(
                    conn,
                    organization_id,
                    company_id,
                )

                row = conn.execute(
                    """SELECT *
                       FROM discovery_search_history
                       WHERE id=?
                         AND organization_id=?
                         AND company_id=?""",
                    (
                        int(history_id),
                        int(organization_id),
                        int(company_id),
                    ),
                ).fetchone()

            return (
                self
                ._deserialize_discovery_search_history(
                    row
                )
                if row is not None
                else None
            )

        except DatabaseAuthorizationError:
            raise

        except (
            sqlite3.Error,
            StorageError,
            ValueError,
            TypeError,
        ):
            raise DatabaseError(
                "Could not read discovery history."
            ) from None

    def page_discovery_history(self, account_id, organization_id, company_id, *,
                               page_size=20, state=None, start=None, end=None, read_limits=None):
        """Read-only keyset over persisted second-resolution UTC search events."""
        from datetime import timedelta
        if type(page_size) is not int or not 1 <= page_size <= 20:
            raise ValueError('Page size must be 1..20.')
        def bound(value):
            if value is None:
                return None
            instant = datetime.fromisoformat(value)
            if instant.microsecond:
                instant = instant.replace(microsecond=0) + timedelta(seconds=1)
            return instant.isoformat(timespec='seconds')
        try:
            with closing(self._connect()) as conn, bounded_read(conn, read_limits), conn:
                conn.execute('BEGIN')
                self._require_org_role(conn, account_id, organization_id)
                self._require_company_scope(conn, organization_id, company_id)
                if state is None:
                    fence = conn.execute('SELECT COALESCE(MAX(id),0) FROM discovery_search_history').fetchone()[0]
                    state = {'fence': fence, 'as_of': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                             'after': None, 'observed_count': None, 'read_count': 0}
                clause = 'organization_id=? AND company_id=? AND id<=? AND created_at<=?'
                params = [organization_id, company_id, state['fence'], state['as_of']]
                for operator, value in [('>=', start), ('<', end)]:
                    if value is not None:
                        clause += ' AND created_at' + operator + '?'
                        params.append(bound(value))
                count = (preflight(conn, clause, params, read_limits) if read_limits is not None else
                         conn.execute('SELECT COUNT(*) FROM discovery_search_history WHERE ' + clause, params).fetchone()[0])
                original_count = count if state['observed_count'] is None else state['observed_count']
                if state['after'] is not None:
                    clause += ' AND (created_at<? OR (created_at=? AND id<?))'
                    stamp, identity = state['after']
                    params.extend([stamp, stamp, identity])
                rows = conn.execute('SELECT * FROM discovery_search_history WHERE ' + clause +
                                    ' ORDER BY created_at DESC,id DESC LIMIT ?', (*params, page_size + 1)).fetchall()
                more = len(rows) > page_size
                rows = rows[:page_size]
                records = [self._deserialize_discovery_search_history(row) for row in rows]
                next_state = dict(state, observed_count=original_count,
                                  read_count=state['read_count'] + len(records))
                if records:
                    next_state['after'] = [records[-1].created_at, records[-1].id]
                return {'records': records, 'state': next_state, 'has_more': more,
                        'observed_count': original_count, 'remaining_storage_count': count,
                        'completeness': 'complete_observed_storage' if count == original_count else 'incomplete_deleted_events',
                        'storage_state': 'available'}
        except DatabaseAuthorizationError:
            raise
        except (sqlite3.Error, StorageError, ValueError, TypeError):
            raise DatabaseError('Could not page discovery history.') from None

    def find_by_hash(self, owner_user_id: int, pdf_sha256: str) -> StoredTender | None:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM tenders WHERE owner_user_id=? AND pdf_sha256=?",
                    (owner_user_id, pdf_sha256),
                ).fetchone()
            return self._deserialize(row) if row else None
        except (sqlite3.Error, StorageError):
            raise DatabaseError("Не удалось прочитать локальную базу данных.") from None

    def find_by_id(self, owner_user_id: int, tender_id: int) -> StoredTender | None:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM tenders WHERE owner_user_id=? AND id=?",
                    (owner_user_id, int(tender_id)),
                ).fetchone()
            return self._deserialize(row) if row else None
        except (sqlite3.Error, StorageError, ValueError, TypeError):
            raise DatabaseError("Не удалось прочитать локальную базу данных.") from None

    def save_success(
        self,
        *,
        owner_user_id: int,
        chat_id: int,
        pdf_sha256: str,
        source_filename: str,
        pages: int | None,
        characters: int,
        analysis: TenderAnalysis,
        scoring: ScoringResult | None,
        analysis_truncated: bool,
    ) -> StoredTender:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        analysis_json = analysis.model_dump_json()
        scoring_json = scoring.model_dump_json() if scoring is not None else None
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO tenders(
                            owner_user_id, chat_id, pdf_sha256, source_filename, pages,
                            characters, analysis_json, scoring_json, analysis_truncated,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(owner_user_id, pdf_sha256) DO UPDATE SET
                            chat_id=excluded.chat_id,
                            source_filename=excluded.source_filename,
                            pages=excluded.pages,
                            characters=excluded.characters,
                            analysis_json=excluded.analysis_json,
                            scoring_json=excluded.scoring_json,
                            analysis_truncated=excluded.analysis_truncated,
                            updated_at=excluded.updated_at
                        """,
                        (
                            owner_user_id,
                            chat_id,
                            pdf_sha256,
                            source_filename,
                            pages,
                            characters,
                            analysis_json,
                            scoring_json,
                            int(analysis_truncated),
                            now,
                            now,
                        ),
                    )
                    row = conn.execute(
                        "SELECT * FROM tenders WHERE owner_user_id=? AND pdf_sha256=?",
                        (owner_user_id, pdf_sha256),
                    ).fetchone()
            if row is None:
                raise DatabaseError("Не удалось сохранить тендер.")
            return self._deserialize(row)
        except (sqlite3.Error, StorageError):
            raise DatabaseError("Не удалось сохранить тендер в локальную базу данных.") from None

    def list_recent(self, owner_user_id: int, limit: int = 10) -> list[StoredTender]:
        limit = max(1, min(int(limit), 20))
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT * FROM tenders WHERE owner_user_id=? "
                    "ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (owner_user_id, limit),
                ).fetchall()
            return [self._deserialize(row) for row in rows]
        except (sqlite3.Error, StorageError):
            raise DatabaseError("Не удалось получить историю тендеров.") from None
