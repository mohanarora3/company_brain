"""The web API, served for real on a free port and called over HTTP."""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from urllib.request import Request, urlopen

import uvicorn

from lastday import server
from lastday.meterless.client import stop_bridge

from .helpers import seed_dir


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_dir(42)
        cls.port = _free_port()
        cls.srv = uvicorn.Server(uvicorn.Config(server.make_app(), host="127.0.0.1", port=cls.port, log_level="error"))
        threading.Thread(target=cls.srv.run, daemon=True).start()
        for _ in range(100):
            if cls.srv.started:
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.srv.should_exit = True
        stop_bridge()

    def call(self, path: str, body=None):
        req = Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body is not None else None,
                      method="POST" if body is not None else "GET", headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if r.headers.get("content-type", "").startswith("application/json") else raw

    def test_page_and_status(self):
        self.assertIn("Last Day", self.call("/"))
        st = self.call("/api/status")
        self.assertEqual(st["federation"]["engine"], "local")
        self.assertTrue(st["governance"]["read_only"])

    def test_people_lists_departures(self):
        out = self.call("/api/people")
        leaving = [p for p in out["people"] if p.get("last_day")]
        self.assertTrue(leaving)
        self.assertIn("days_left", leaving[0])

    def test_run_stream_and_download(self):
        eid = next(p for p in self.call("/api/people")["people"] if p.get("days_left", -1) >= 0)["employee_id"]
        rid = self.call("/api/runs", {"employee_id": eid, "use_memory": False})["run_id"]
        events = []
        with urlopen(f"http://127.0.0.1:{self.port}/api/runs/{rid}/events", timeout=120) as r:
            for line in r:
                line = line.decode().strip()
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))
                if line == "event: end":
                    break
        self.assertTrue(any(e["kind"] == "done" for e in events))
        snap = self.call(f"/api/runs/{rid}")
        self.assertEqual(snap["status"], "done")
        self.assertTrue(snap["evidence"])
        md = self.call(f"/api/runs/{rid}/files/handover.md")
        self.assertIn("# Handover plan", md)

    def test_sources_and_outage_toggle(self):
        self.assertIn("pagerduty", self.call("/api/sources")["all_sources"])
        self.assertEqual(self.call("/api/sources/jira/fail", {"on": True})["failing"], ["jira"])
        self.assertEqual(self.call("/api/sources/jira/fail", {"on": False})["failing"], [])


if __name__ == "__main__":
    unittest.main()
