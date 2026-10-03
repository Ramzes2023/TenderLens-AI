import sqlite3
from contextlib import closing
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app.auth import AuthRepository, AuthService
from app.organizations import OrganizationRepository, OrganizationService, OrganizationError, Role


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        self.auth = AuthRepository(self.path)
        self.auth.initialize()
        self.repo = OrganizationRepository(self.path)
        self.service = OrganizationService(self.repo)
        self.a = self.auth.create_account("a@example.com", "synthetic")
        self.b = self.auth.create_account("b@example.com", "synthetic")

    def test_new_account_exactly_one_owner_org(self):
        orgs = self.repo.list_for_account(self.a.id)
        self.assertEqual(len(orgs), 1)
        self.assertEqual(self.repo.get_membership(orgs[0].id, self.a.id).role, Role.OWNER)
        self.assertEqual(self.repo.default_for_account(self.a.id), orgs[0])

    def test_idempotent_startup(self):
        for _ in range(3):
            self.auth.initialize()
            self.repo.initialize()
        self.assertEqual(len(self.repo.list_for_account(self.a.id)), 1)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM organization_members").fetchone()[0], 2)

    def test_existing_account_and_company_backfill(self):
        legacy = Path(self.temp.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as conn:
            conn.executescript("""
                CREATE TABLE auth_accounts(id INTEGER PRIMARY KEY,email TEXT,password_hash TEXT,
                    owner_user_id INTEGER UNIQUE,is_active INTEGER,created_at TEXT,updated_at TEXT);
                INSERT INTO auth_accounts VALUES(7,'old@example.com','synthetic',777,1,'old','old');
                CREATE TABLE company_workspaces(id INTEGER PRIMARY KEY,owner_user_id INTEGER,name TEXT);
                INSERT INTO company_workspaces VALUES(8,777,'AluTrade');
                INSERT INTO company_workspaces VALUES(9,999,'Telegram only');
            """)
        repo = OrganizationRepository(legacy)
        repo.initialize()
        repo.initialize()
        org = repo.default_for_account(7)
        with closing(sqlite3.connect(legacy)) as conn:
            self.assertEqual(conn.execute("SELECT id,owner_user_id,organization_id FROM company_workspaces ORDER BY id").fetchall(),
                             [(8,777,org.id),(9,999,None)])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auth_accounts").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_invalid_and_duplicate_membership(self):
        org = self.repo.default_for_account(self.a.id)
        with self.assertRaises(ValueError):
            self.repo.add_membership(org.id, self.b.id, "superuser")
        with self.assertRaises(OrganizationError):
            self.repo.add_membership(org.id, self.a.id, Role.VIEWER)
        self.assertEqual(self.repo.get_membership(org.id,self.a.id).role,Role.OWNER)
        with closing(sqlite3.connect(self.path)) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO organization_members VALUES(?,?,?,?)", (org.id,self.b.id,"bad","now"))

    def test_scoped_lookup_and_allowed_roles(self):
        org = self.repo.default_for_account(self.a.id)
        self.assertNotIn(org.id, [o.id for o in self.service.list_for_account(self.b)])
        self.assertIsNone(self.repo.get_membership(org.id,self.b.id))
        with self.assertRaises(OrganizationError):
            self.service.get(self.b,org.id)
        self.repo.add_membership(org.id,self.b.id,Role.VIEWER)
        with self.assertRaises(OrganizationError):
            self.service.require_membership(self.b,org.id,{Role.ADMIN,Role.OWNER})
        self.service.require_membership(self.b,org.id,{Role.VIEWER})
        with self.assertRaises(OrganizationError):
            self.service.require_membership(replace(self.a,is_active=False),org.id)
        with self.assertRaises(OrganizationError):
            self.service.require_membership(self.a,org.id,set())

    def test_last_owner_and_transfer(self):
        org = self.repo.create("Shared",self.a.id)
        with self.assertRaises(OrganizationError):
            self.repo.remove_membership(org.id,self.a.id)
        with self.assertRaises(OrganizationError):
            self.repo.update_role(org.id,self.a.id,Role.ADMIN)
        self.repo.add_membership(org.id,self.b.id,Role.OWNER)
        self.repo.update_role(org.id,self.a.id,Role.MEMBER)
        self.repo.remove_membership(org.id,self.a.id)
        self.assertEqual(len(self.repo.list_memberships(org.id)),1)
        with self.assertRaises(OrganizationError):
            self.repo.remove_membership(org.id,self.b.id)

    def test_personal_owner_not_recreated_after_removal(self):
        org = self.repo.default_for_account(self.a.id)
        self.repo.add_membership(org.id,self.b.id,Role.OWNER)
        with self.assertRaises(OrganizationError):
            self.repo.remove_membership(org.id,self.a.id)

    def test_concurrent_defaults(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DELETE FROM organization_members WHERE organization_id IN (SELECT id FROM organizations WHERE personal_account_id=?)", (self.a.id,))
            conn.execute("DELETE FROM organizations WHERE personal_account_id=?", (self.a.id,))
            conn.commit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: OrganizationRepository(self.path).default_for_account(self.a.id).id, range(12)))
        self.assertEqual(len(set(results)),1)
        self.assertEqual(len(self.repo.list_for_account(self.a.id)),1)

    def test_company_creation_and_linking_keep_ids_and_owners(self):
        from app.companies import CompanyRepository
        from app.scoring.models import CompanyProfile
        companies = CompanyRepository(self.path)
        companies.initialize()
        profile = CompanyProfile(profile_version="test",company_name="AluTrade",
                                 product_keywords=["aluminium"])
        legacy = companies.create(123456789,"AluTrade",profile)
        web = companies.create(self.a.owner_user_id,"Web company",profile)
        org = self.repo.default_for_account(self.a.id)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertIsNone(conn.execute("SELECT organization_id FROM company_workspaces WHERE id=?", (legacy.id,)).fetchone()[0])
            self.assertEqual(conn.execute("SELECT organization_id FROM company_workspaces WHERE id=?", (web.id,)).fetchone()[0],org.id)
        self.auth.link_owner(self.a.id,123456789)
        self.assertEqual(companies.get(123456789,legacy.id).name,"AluTrade")
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT organization_id FROM company_workspaces WHERE id=?", (legacy.id,)).fetchone()[0],org.id)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_scoped_company_backfill_only_updates_requested_owner(self):
        from app.companies import CompanyRepository
        from app.organizations.migration import backfill_companies
        from app.scoring.models import CompanyProfile

        companies = CompanyRepository(self.path)
        companies.initialize()

        profile = CompanyProfile(
            profile_version="test",
            company_name="Scoped",
            product_keywords=["aluminium"],
        )

        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """INSERT INTO company_workspaces(
                    owner_user_id, name, profile_json,
                    created_at, updated_at, organization_id
                ) VALUES (?, ?, ?, ?, ?, NULL)""",
                (
                    self.a.owner_user_id,
                    "Scoped A",
                    profile.model_dump_json(),
                    "now",
                    "now",
                ),
            )
            conn.execute(
                """INSERT INTO company_workspaces(
                    owner_user_id, name, profile_json,
                    created_at, updated_at, organization_id
                ) VALUES (?, ?, ?, ?, ?, NULL)""",
                (
                    self.b.owner_user_id,
                    "Scoped B",
                    profile.model_dump_json(),
                    "now",
                    "now",
                ),
            )
            conn.commit()

        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            backfill_companies(conn, self.a.owner_user_id)
            conn.commit()

            rows = conn.execute(
                """SELECT owner_user_id, organization_id
                   FROM company_workspaces
                   WHERE name IN ('Scoped A', 'Scoped B')
                   ORDER BY owner_user_id"""
            ).fetchall()

        org_a = self.repo.default_for_account(self.a.id)

        by_owner = {int(owner): org_id for owner, org_id in rows}
        self.assertEqual(
            by_owner[self.a.owner_user_id],
            org_a.id,
        )
        self.assertIsNone(
            by_owner[self.b.owner_user_id]
        )

    def test_concurrent_initialize_remains_idempotent(self):
        def initialize(_):
            OrganizationRepository(self.path).initialize()
            return True

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(
                sum(pool.map(initialize, range(8))),
                8,
            )

        with closing(sqlite3.connect(self.path)) as conn:
            personal = conn.execute(
                "SELECT COUNT(*) FROM organizations "
                "WHERE personal_account_id IS NOT NULL"
            ).fetchone()[0]
            memberships = conn.execute(
                "SELECT COUNT(*) FROM organization_members"
            ).fetchone()[0]

        self.assertEqual(personal, 2)
        self.assertEqual(memberships, 2)

    def test_concurrent_owner_removal(self):
        org = self.repo.create("Shared",self.a.id)
        self.repo.add_membership(org.id,self.b.id,Role.OWNER)
        def remove(account):
            try:
                OrganizationRepository(self.path).remove_membership(org.id,account.id)
                return True
            except OrganizationError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(remove,[self.a,self.b])),1)
        self.assertEqual(self.repo.list_memberships(org.id)[0].role,Role.OWNER)

    def test_registration_rolls_back_if_org_creation_fails(self):
        with patch("app.auth.repository.ensure_personal",side_effect=sqlite3.IntegrityError()):
            with self.assertRaises(Exception):
                self.auth.create_account("fail@example.com","synthetic")
        self.assertIsNone(self.auth.find_account_by_email("fail@example.com"))

    def test_telegram_link_preserves_org_and_session(self):
        service = AuthService(self.auth)
        org = self.repo.default_for_account(self.a.id)
        session = service.create_session(self.a)
        ticket,_ = service.create_telegram_link(self.a)
        service.consume_telegram_link(ticket,123456789)
        current = service.account_for_token(session)
        self.assertEqual(current.owner_user_id,123456789)
        self.assertEqual(self.repo.default_for_account(current.id).id,org.id)

    def test_no_partial_org_for_missing_account(self):
        with self.assertRaises(OrganizationError):
            self.repo.create("Orphan",999999)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM organizations WHERE name='Orphan'").fetchone()[0],0)
