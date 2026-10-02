import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Use dummy values so tests never contact a real Supabase project.
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-role-key"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"

import servidor  # noqa: E402


class FakeDatabase:
    def __init__(self):
        self.records = {}

    def table(self, name):
        if name != "contenido_secciones":
            raise AssertionError("Unexpected table: " + name)
        return FakeQuery(self)


class FakeQuery:
    def __init__(self, database):
        self.database = database
        self.allowed_sections = None
        self.upsert_row = None

    def select(self, _columns):
        return self

    def in_(self, _column, values):
        self.allowed_sections = set(values)
        return self

    def upsert(self, row, on_conflict=None):
        if on_conflict != "seccion":
            raise AssertionError("Unexpected conflict target")
        self.upsert_row = row
        return self

    def execute(self):
        if self.upsert_row is not None:
            row = dict(self.upsert_row)
            self.database.records[row["seccion"]] = row
            return SimpleNamespace(data=[row])

        rows = list(self.database.records.values())
        if self.allowed_sections is not None:
            rows = [row for row in rows if row["seccion"] in self.allowed_sections]
        return SimpleNamespace(data=rows)


class EditorialSectionsApiTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        servidor.supabase = self.database
        servidor.supabase_admin = self.database
        servidor.SUPABASE_CONFIG_ERROR = None
        servidor.SUPABASE_WRITE_KEY = "test-service-role-key"
        servidor.ADMIN_PASSWORD = "test-admin-password"
        self.client = servidor.app.test_client()

    def test_public_read_returns_both_sections(self):
        response = self.client.get("/api/secciones")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "success": True,
            "secciones": {"vida": None, "obra": None},
        })

    def test_public_read_returns_saved_text(self):
        self.database.records["vida"] = {
            "seccion": "vida",
            "contenido": "Biografía actualizada",
            "updated_at": "2026-10-02T00:00:00+00:00",
        }
        response = self.client.get("/api/secciones")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["secciones"]["vida"], "Biografía actualizada")
        self.assertIsNone(response.get_json()["secciones"]["obra"])

    def test_write_requires_admin_password(self):
        response = self.client.put("/api/secciones/vida", json={"contenido": "No autorizado"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.database.records, {})

    def test_admin_can_save_and_public_can_read(self):
        response = self.client.put(
            "/api/secciones/obra",
            json={"contenido": "Pensamiento y legado\nSegundo párrafo."},
            headers={"X-Admin-Password": "test-admin-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

        public_response = self.client.get("/api/secciones")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(
            public_response.get_json()["secciones"]["obra"],
            "Pensamiento y legado\nSegundo párrafo.",
        )

    def test_rejects_unknown_section_and_non_text_content(self):
        headers = {"X-Admin-Password": "test-admin-password"}
        unknown = self.client.put(
            "/api/secciones/videos", json={"contenido": "x"}, headers=headers
        )
        invalid = self.client.put(
            "/api/secciones/vida", json={"contenido": ["no", "text"]}, headers=headers
        )
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.database.records, {})


if __name__ == "__main__":
    unittest.main()
