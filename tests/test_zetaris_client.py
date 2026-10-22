"""The Zetaris client against a stand-in HTTP server that speaks the same API.

No Zetaris instance is needed: the fake checks the headers the real API
requires (Bearer key, numeric X-Org-ID, UUID X-Request-ID) and answers in the
shapes the client must handle (rows as objects, rows as arrays with a header,
rows as arrays without one).
"""
from __future__ import annotations

import json
import threading
import unittest
import uuid
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lastday.config import SETTINGS
from lastday.federation import FederationError, ZetarisFederation
from lastday.federation.governance import GovernanceError

SEEN: list[dict] = []


class FakeZetaris(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._send(401, {"message": "invalid token"})
        if not (self.headers.get("X-Org-ID") or "").isdigit():
            return self._send(400, {"message": "bad org"})
        try:
            uuid.UUID(self.headers.get("X-Request-ID", ""))
        except ValueError:
            return self._send(400, {"message": "bad request id"})
        sql = body["sql"]
        if "objects" in sql:
            return self._send(200, {"data": [{"name": "Priya Raman", "n": "29"}, {"name": "Rahul Verma", "n": "7"}]})
        if "header" in sql:
            return self._send(200, {"columns": [{"name": "name"}, {"name": "n"}], "data": [["Priya Raman", "29"]]})
        if "bare" in sql:
            return self._send(200, {"data": [["Priya Raman", "29", "null"]]})
        if "flaky" in sql:
            return self._send(200, {"status": "FAILED", "error": "table not found: jira.issuez"})
        return self._send(200, {"data": [["1"]]})

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ZetarisClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeZetaris)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        port = cls.srv.server_address[1]
        cls.s = replace(SETTINGS, zetaris_rest_url=f"http://127.0.0.1:{port}/api/v1.0", zetaris_api_key="test-key",
                        zetaris_org_id="1001", zetaris_base_url="")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def fed(self, **kw) -> ZetarisFederation:
        return ZetarisFederation(replace(self.s, **kw), cache_ttl=0)

    def test_rest_route_and_headers(self):
        SEEN.clear()
        r = self.fed().query("SELECT 1 AS one")
        self.assertEqual(r.first("one"), "1")
        req = SEEN[-1]
        self.assertEqual(req["path"], "/api/v1.0/sql-editor/sqls/run")
        self.assertEqual(req["body"]["source"], "SqlEditor")
        self.assertEqual(req["headers"]["x-org-id"], "1001")
        uuid.UUID(req["headers"]["x-request-id"])
        self.assertEqual(req["headers"]["authorization"], "Bearer test-key")

    def test_rows_as_objects(self):
        r = self.fed().query("SELECT name AS name, n AS n FROM objects.t", numeric=("n",))
        self.assertEqual(r.rows[0], {"name": "Priya Raman", "n": 29})

    def test_rows_with_header(self):
        r = self.fed().query("SELECT name AS name, n AS n FROM header.t", numeric=("n",))
        self.assertEqual(r.rows, [{"name": "Priya Raman", "n": 29}])

    def test_rows_without_header_use_select_aliases(self):
        r = self.fed().query("SELECT e.full_name AS name, COUNT(*) AS n, MAX(x) AS last FROM bare.t e", numeric=("n",))
        self.assertEqual(r.rows, [{"name": "Priya Raman", "n": 29, "last": None}])

    def test_engine_errors_become_federation_errors(self):
        with self.assertRaises(FederationError):
            self.fed().query("SELECT a AS a FROM flaky.t")

    def test_bad_key_is_explained(self):
        with self.assertRaises(FederationError) as cm:
            self.fed(zetaris_api_key="wrong").query("SELECT 1 AS one")
        self.assertIn("401", str(cm.exception))

    def test_governance_runs_before_the_network(self):
        SEEN.clear()
        with self.assertRaises(GovernanceError):
            self.fed().query("SELECT salary_band FROM hr_pg.employees_directory")
        self.assertEqual(SEEN, [])

    def test_status(self):
        st = self.fed().status()
        self.assertTrue(st["connected"])
        self.assertEqual(st["route"], "rest")


if __name__ == "__main__":
    unittest.main()
