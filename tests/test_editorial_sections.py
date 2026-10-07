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
        self.publications = []
        self.comments = []
        self.subscribers = []
        self.contact = {
            "id": 1,
            "whatsapp": "",
            "email": "",
            "messenger_url": "",
            "tiktok_handle": "",
        }

    def table(self, name):
        if name == "contenido_secciones":
            return FakeQuery(self)
        if name == "publicaciones":
            return FakePublicationQuery(self)
        if name == "comentarios":
            return FakeCommentQuery(self)
        if name == "suscriptores":
            return FakeSubscriberQuery(self)
        if name == "contacto_publico":
            return FakeContactQuery(self)
        raise AssertionError("Unexpected table: " + name)


class FakeQuery:
    def __init__(self, database):
        self.database = database
        self.allowed_sections = None
        self.filters = {}
        self.upsert_row = None
        self.deleting = False

    def select(self, _columns):
        return self

    def in_(self, _column, values):
        self.allowed_sections = set(values)
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, _count):
        return self

    def upsert(self, row, on_conflict=None):
        if on_conflict != "seccion":
            raise AssertionError("Unexpected conflict target")
        self.upsert_row = row
        return self

    def delete(self):
        self.deleting = True
        return self

    def execute(self):
        if self.upsert_row is not None:
            row = dict(self.upsert_row)
            self.database.records[row["seccion"]] = row
            return SimpleNamespace(data=[row])

        if self.deleting:
            deleted = [
                row for row in self.database.records.values()
                if all(row.get(key) == value for key, value in self.filters.items())
            ]
            for row in deleted:
                self.database.records.pop(row["seccion"], None)
            return SimpleNamespace(data=deleted)

        rows = list(self.database.records.values())
        if self.allowed_sections is not None:
            rows = [row for row in rows if row["seccion"] in self.allowed_sections]
        for key, value in self.filters.items():
            rows = [row for row in rows if row.get(key) == value]
        return SimpleNamespace(data=rows)


class FakePublicationQuery:
    def __init__(self, database):
        self.database = database
        self.filters = {}
        self.insert_row = None
        self.deleting = False
        self.range_bounds = None

    def range(self, start, end):
        self.range_bounds = (start, end)
        return self

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def order(self, _column, desc=False):
        return self

    def limit(self, _count):
        return self

    def insert(self, row):
        self.insert_row = dict(row)
        return self

    def delete(self):
        self.deleting = True
        return self

    def execute(self):
        if self.insert_row is not None:
            self.database.publications.append(self.insert_row)
            return SimpleNamespace(data=[self.insert_row])

        if self.deleting:
            deleted = [
                row for row in self.database.publications
                if all(row.get(key) == value for key, value in self.filters.items())
            ]
            self.database.publications = [
                row for row in self.database.publications if row not in deleted
            ]
            return SimpleNamespace(data=deleted)

        rows = list(self.database.publications)
        for key, value in self.filters.items():
            rows = [row for row in rows if row.get(key) == value]
        if self.range_bounds is not None:
            start, end = self.range_bounds
            rows = rows[start:end + 1]
        return SimpleNamespace(data=rows)


class FakeCommentQuery:
    def __init__(self, database):
        self.database = database
        self.filters = {}
        self.insert_row = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def order(self, _column, desc=False):
        return self

    def limit(self, _count):
        return self

    def insert(self, row):
        self.insert_row = dict(row)
        return self

    def execute(self):
        if self.insert_row is not None:
            row = dict(self.insert_row)
            row.update({"id": "comment-1", "created_at": "2026-10-04T00:00:00+00:00"})
            self.database.comments.append(row)
            return SimpleNamespace(data=[row])

        rows = list(self.database.comments)
        for key, value in self.filters.items():
            rows = [row for row in rows if row.get(key) == value]
        return SimpleNamespace(data=rows)


class FakeSubscriberQuery:
    def __init__(self, database):
        self.database = database
        self.insert_row = None

    def select(self, _columns, count=None, head=False):
        return self

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        if on_conflict != "email" or not ignore_duplicates:
            raise AssertionError("Unexpected subscriber upsert options")
        self.insert_row = dict(row)
        return self

    def execute(self):
        if self.insert_row is not None:
            exists = any(row["email"] == self.insert_row["email"] for row in self.database.subscribers)
            if exists:
                return SimpleNamespace(data=[])
            self.database.subscribers.append(self.insert_row)
            return SimpleNamespace(data=[self.insert_row])
        return SimpleNamespace(data=[], count=len(self.database.subscribers))


class FakeContactQuery:
    def __init__(self, database):
        self.database = database
        self.filters = {}
        self.upsert_row = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, _count):
        return self

    def upsert(self, row, on_conflict=None):
        if on_conflict != "id":
            raise AssertionError("Unexpected contact conflict target")
        self.upsert_row = dict(row)
        return self

    def execute(self):
        if self.upsert_row is not None:
            self.database.contact = dict(self.upsert_row)
            return SimpleNamespace(data=[self.database.contact])
        if all(self.database.contact.get(key) == value for key, value in self.filters.items()):
            return SimpleNamespace(data=[self.database.contact])
        return SimpleNamespace(data=[])


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
            "secciones": {"vida": "", "obra": ""},
            "archivos": {"vida": None, "obra": None},
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
        self.assertEqual(response.get_json()["secciones"]["obra"], "")

    def test_admin_can_save_multipart_content_for_vida(self):
        response = self.client.put(
            "/api/secciones/vida",
            data={"contenido": "Título biográfico\n\nHistoria"},
            headers={"X-Admin-Password": "test-admin-password"},
        )
        self.assertEqual(response.status_code, 200)
        public_response = self.client.get("/api/secciones")
        self.assertEqual(
            public_response.get_json()["secciones"]["vida"],
            "Título biográfico\n\nHistoria",
        )

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

    def test_admin_can_delete_saved_editorial_section(self):
        self.database.records["obra"] = {
            "seccion": "obra",
            "contenido": "Texto con un error que se va a corregir.",
            "archivo_url": None,
        }

        response = self.client.delete(
            "/api/secciones/obra",
            headers={"X-Admin-Password": "test-admin-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertFalse(response.get_json()["already_empty"])
        self.assertNotIn("obra", self.database.records)

    def test_admin_can_clear_draft_when_editorial_section_is_already_empty(self):
        response = self.client.delete(
            "/api/secciones/obra",
            headers={"X-Admin-Password": "test-admin-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "success": True,
            "seccion": "obra",
            "archivo_eliminado": False,
            "already_empty": True,
        })

    def test_editorial_delete_requires_admin_password(self):
        response = self.client.delete("/api/secciones/obra")
        self.assertEqual(response.status_code, 401)

    def test_empty_editorial_section_delete_button_can_be_used_for_drafts(self):
        admin_html = (ROOT / "admin.html").read_text(encoding="utf-8")
        self.assertIn("if (button) button.disabled = false;", admin_html)
        self.assertIn("limpiar el borrador", admin_html)

    def test_public_header_restores_historical_motto(self):
        public_html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('<p class="header-lema">El sueño del hombre</p>', public_html)
        self.assertIn(".header-institucional .header-lema", (ROOT / "style.css").read_text(encoding="utf-8"))
        self.assertIn("<title>Alfredo Maneiro</title>", public_html)
        self.assertIn('"@type": "WebSite"', public_html)
        self.assertIn('"name": "Alfredo Maneiro"', public_html)
        self.assertIn('property="og:site_name" content="Alfredo Maneiro"', public_html)
        self.assertIn('property="og:title" content="Alfredo Maneiro"', public_html)
        self.assertIn('name="twitter:title" content="Alfredo Maneiro"', public_html)
        self.assertNotIn("portal", public_html.lower())
        admin_html = (ROOT / "admin.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex, nofollow">', admin_html)

    def test_search_engines_can_fetch_robots_and_sitemap(self):
        robots = self.client.get("/robots.txt")
        sitemap = self.client.get("/sitemap.xml")

        self.assertEqual(robots.status_code, 200)
        self.assertIn("text/plain", robots.content_type)
        reglas_robots = robots.get_data(as_text=True).splitlines()
        self.assertIn("Allow: /", reglas_robots)
        self.assertNotIn("Disallow: /", reglas_robots)
        self.assertIn("Disallow: /api/", reglas_robots)
        self.assertEqual(
            robots.headers.get("Cache-Control"),
            "public, max-age=0, must-revalidate",
        )
        self.assertIn("Sitemap: https://alfredomaneiro.org.ve/sitemap.xml", robots.get_data(as_text=True))
        self.assertEqual(sitemap.status_code, 200)
        self.assertIn("application/xml", sitemap.content_type)
        self.assertIn("<loc>https://alfredomaneiro.org.ve/</loc>", sitemap.get_data(as_text=True))

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

    def test_publications_api_lists_by_section(self):
        self.database.publications = [
            {"id": "1", "titulo": "Inicio", "seccion": "inicio"},
            {"id": "2", "titulo": "Foto", "seccion": "fotos"},
        ]
        response = self.client.get("/api/publicaciones?seccion=inicio")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.get_json()["publicaciones"]],
            ["1"],
        )

    def test_publication_creation_requires_admin(self):
        response = self.client.post(
            "/api/publicaciones",
            data={"seccion": "inicio", "titulo": "No autorizado"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.database.publications, [])

    def test_admin_can_create_and_delete_publication(self):
        headers = {"X-Admin-Password": "test-admin-password"}
        created = self.client.post(
            "/api/publicaciones",
            data={"seccion": "inicio", "titulo": "Aviso", "texto": "Contenido"},
            headers=headers,
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.get_json()["success"])
        publication_id = created.get_json()["publicacion"]["id"]

        deleted = self.client.delete(
            "/api/publicaciones/" + publication_id,
            headers=headers,
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.database.publications, [])

    def test_public_comments_can_be_created_and_listed(self):
        self.database.publications = [{"id": "post-1"}]
        created = self.client.post(
            "/api/publicaciones/post-1/comentarios",
            json={"texto": "Muy buen artículo."},
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.get_json()["success"])

        listed = self.client.get("/api/publicaciones/post-1/comentarios")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["comentarios"]), 1)
        self.assertEqual(listed.get_json()["comentarios"][0]["texto"], "Muy buen artículo.")

    def test_subscription_signup_is_idempotent_and_counted(self):
        first = self.client.post("/api/suscripciones", json={"email": "lector@example.com"})
        second = self.client.post("/api/suscripciones", json={"email": "LECTOR@example.com"})
        count = self.client.get("/api/suscripciones/count")

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.get_json()["alreadySubscribed"])
        self.assertTrue(second.get_json()["alreadySubscribed"])
        self.assertEqual(count.status_code, 200)
        self.assertEqual(count.get_json()["count"], 1)

    def test_subscription_rejects_invalid_email(self):
        response = self.client.post("/api/suscripciones", json={"email": "not-an-email"})
        self.assertEqual(response.status_code, 400)

    def test_public_contact_channels_can_be_read_and_updated_by_admin(self):
        headers = {"X-Admin-Password": "test-admin-password"}
        channels = {
            "whatsapp": "+58 412-1234567",
            "email": "contacto@example.com",
            "messenger_url": "https://m.me/portal",
            "tiktok_handle": "@portal.maneiro",
        }
        updated = self.client.put("/api/contacto-publico", json=channels, headers=headers)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["contacto"]["tiktok_handle"], "@portal.maneiro")

        public = self.client.get("/api/contacto-publico")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.get_json()["contacto"]["email"], "contacto@example.com")

    def test_contact_write_requires_admin_and_rejects_untrusted_url(self):
        unauthenticated = self.client.put(
            "/api/contacto-publico", json={"email": "contacto@example.com"}
        )
        invalid = self.client.put(
            "/api/contacto-publico",
            json={"messenger_url": "javascript:alert(1)"},
            headers={"X-Admin-Password": "test-admin-password"},
        )
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(invalid.status_code, 400)

    def test_contact_delete_requires_admin_and_clears_all_channels(self):
        self.database.contact.update({
            "whatsapp": "+58 412-1234567",
            "email": "contacto@example.com",
            "messenger_url": "https://m.me/portal",
            "tiktok_handle": "@portal.maneiro",
        })

        unauthenticated = self.client.delete("/api/contacto-publico")
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(self.database.contact["email"], "contacto@example.com")

        deleted = self.client.delete(
            "/api/contacto-publico",
            headers={"X-Admin-Password": "test-admin-password"},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.get_json()["success"])
        self.assertEqual(
            {field: self.database.contact[field] for field in servidor.CONTACTO_VACIO},
            servidor.CONTACTO_VACIO,
        )

        public = self.client.get("/api/contacto-publico")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.get_json()["contacto"], servidor.CONTACTO_VACIO)

    def test_public_contact_view_replaces_the_static_form(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        admin_html = (ROOT / "admin.html").read_text(encoding="utf-8")
        self.assertIn('id="contacto-canales"', html)
        self.assertNotIn('id="form-contacto"', html)
        self.assertIn("/api/contacto-publico", html)
        for field in ("whatsapp", "email", "messenger", "tiktok"):
            self.assertIn("admin-contacto-" + field, admin_html)
        self.assertIn('id="btn-eliminar-contacto"', admin_html)
        self.assertIn("eliminarContactoAdmin(event)", admin_html)

    def test_contact_migration_removes_public_write_policy(self):
        migration = (ROOT / "migrations/20261004_contacto_publico_api.sql").read_text(encoding="utf-8")
        self.assertIn('drop policy if exists "Permitir actualizacion administrativa de contacto"', migration)
        self.assertIn("revoke all on table public.contacto_publico from anon, authenticated", migration)
        self.assertIn("grant select on table public.contacto_publico to anon, authenticated", migration)
        self.assertIn("grant all on table public.contacto_publico to service_role", migration)


class SupabaseUrlNormalizationTests(unittest.TestCase):
    def test_strips_postgrest_suffix(self):
        self.assertEqual(
            servidor.normalizar_supabase_url("https://example.supabase.co/rest/v1/"),
            "https://example.supabase.co",
        )

    def test_preserves_project_root(self):
        self.assertEqual(
            servidor.normalizar_supabase_url("https://example.supabase.co/"),
            "https://example.supabase.co",
        )


if __name__ == "__main__":
    unittest.main()
