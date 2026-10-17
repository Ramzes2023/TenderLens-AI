"""Real SQLite tests for tenant and individual-owned named filters."""
from contextlib import closing
import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository
from app.workspaces.saved_filters import SavedSearchPresets, PresetLimitError, PresetPermissionError, normalized_filters

FIELDS={k:"" for k in ("keyword","source","buyer","currency","value","fit","deadline","published")}


def fixture(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"search-filters.db"))
    db.migrate()
    repo=AuthRepository(db)
    a=repo.create_account("filters-a@example.test","test-hash")
    b=repo.create_account("filters-b@example.test","test-hash")
    v=repo.create_account("filters-v@example.test","test-hash")
    org=OrganizationRepository(db).default_for_account(a.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("INSERT INTO organization_members(organization_id,account_id,role,created_at) "
                         "VALUES (?,?,?,?)",(org.id,v.id,"viewer","now"))
            conn.execute("INSERT INTO company_workspaces(id,organization_id) VALUES (?,?)",(55,org.id))
            conn.execute("INSERT INTO company_workspaces(id,organization_id) VALUES (?,?)",(56,org.id))
    return db,a,b,v,org


def scope(actor,org,company=55):
    return {"account_id":actor.id,"organization_id":org.id,"company_id":company}


def test_named_presets_are_company_and_account_scoped_and_upsert(tmp_path):
    db,a,b,v,org=fixture(tmp_path)
    presets=SavedSearchPresets(db)
    filters={**FIELDS,"keyword":"станки","source":"eis","currency":"RUB","value":"5000"}
    first=presets.save(**scope(a,org),name="Machines",filters=filters)
    assert first["delivery"]=="not_configured"
    assert first["filters"]["keyword"]=="станки"
    updated=presets.save(**scope(a,org),name="Machines",filters={**FIELDS,"keyword":"metal"})
    assert first["id"]==updated["id"] and updated["filters"]["keyword"]=="metal"
    assert len(presets.list(**scope(a,org)))==1
    assert presets.list(**scope(a,org,56))==[]
    assert presets.list(**scope(v,org))==[]
    with pytest.raises(PresetPermissionError):
        presets.list(**scope(b,org))
    with pytest.raises(PresetPermissionError):
        presets.save(**scope(v,org),name="no",filters=FIELDS)
    with pytest.raises(PresetPermissionError):
        presets.save(**scope(a,org,company=5000),name="no",filters=FIELDS)
    with pytest.raises(PresetPermissionError):
        presets.delete(**scope(b,org),preset_id=first["id"])
    presets.delete(**scope(a,org),preset_id=first["id"])
    assert presets.list(**scope(a,org))==[]
    db.close()


def test_limit_20_and_invalid_filters_are_rejected(tmp_path):
    db,a,_,_,org=fixture(tmp_path)
    presets=SavedSearchPresets(db)
    for i in range(20):
        presets.save(**scope(a,org),name=f"Preset {i}",filters=FIELDS)
    with pytest.raises(PresetLimitError):
        presets.save(**scope(a,org),name="Overflow",filters=FIELDS)
    assert len(presets.list(**scope(a,org)))==20
    for invalid in ({**FIELDS,"currency":"US$"}, {**FIELDS,"fit":"101"},
                    {**FIELDS,"value":"100"}, {**FIELDS,"deadline":"2026-13-99"},
                    {**FIELDS,"keyword":"\r"}, {"keyword":"missing fields"}):
        with pytest.raises(ValueError):
            normalized_filters(invalid)
    db.close()
