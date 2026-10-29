import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import draft_requests
import main

REVIEW = {"Authorization": "Bearer review-secret"}
AUTOMATION = {"Authorization": "Bearer test-secret"}
CLAIMED = {
    "request_id": 5,
    "product_id": 77,
    "external_id": "MLB3456789012",
    "title": "Organizador De Cabos",
    "price": "29.90",
    "image_url": "https://http2.mlstatic.com/D_1.jpg",
    "permalink": "https://www.mercadolivre.com.br/p/MLB3456789012",
}


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append(" ".join(sql.split()))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class FakeConn:
    def __init__(self, rows):
        self.cur = FakeCursor(rows)
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def run(fn, rows, *args):
    conn = FakeConn(rows)
    return fn(lambda: conn, *args), conn


class EnqueueTests(unittest.TestCase):
    def test_unknown_product_returns_none(self):
        result, conn = run(draft_requests.enqueue, [None], 999)
        self.assertIsNone(result)
        self.assertFalse(conn.committed)
        self.assertTrue(conn.closed)

    def test_creates_pending_request(self):
        row = {"id": 5, "tenant_id": 1}
        created = {"id": 5, "status": "pending"}
        result, conn = run(draft_requests.enqueue, [row, created], 77)
        self.assertEqual(result, {"id": 5, "status": "pending", "created": True})
        self.assertTrue(conn.committed)

    def test_retries_when_active_request_finishes_midway(self):
        row = {"id": 77, "tenant_id": 1}
        rows = [row, None, None, row, {"id": 6, "status": "pending"}]
        result, _ = run(draft_requests.enqueue, rows, 77)
        self.assertEqual(result, {"id": 6, "status": "pending", "created": True})

    def test_returns_active_request_instead_of_duplicating(self):
        row = {"id": 77, "tenant_id": 1}
        existing = {"id": 4, "status": "running"}
        result, _ = run(draft_requests.enqueue, [row, None, existing], 77)
        self.assertEqual(result, {"id": 4, "status": "running", "created": False})


class ClaimAndFinishTests(unittest.TestCase):
    def test_claim_with_empty_queue_returns_none(self):
        result, conn = run(draft_requests.claim, [None], "viralbarato")
        self.assertIsNone(result)
        self.assertTrue(conn.committed)

    def test_claim_uses_skip_locked_and_builds_catalog_permalink(self):
        claimed = {"id": 5, "product_id": 77}
        product = {"external_id": "MLB3456789012", "title": "Organizador", "price": None, "image_url": None}
        result, conn = run(draft_requests.claim, [claimed, product], "viralbarato")
        self.assertEqual(result["request_id"], 5)
        self.assertEqual(result["permalink"], "https://www.mercadolivre.com.br/p/MLB3456789012")
        self.assertIsNone(result["price"])
        self.assertTrue(any("SKIP LOCKED" in sql for sql in conn.cur.sql))

    def test_finish_unknown_or_not_running_request_returns_false(self):
        ok, conn = run(draft_requests.finish, [None], "viralbarato", 9, "failed", None, "x")
        self.assertEqual(ok, "not_running")
        self.assertFalse(conn.committed)

    def test_finish_completed_requires_post_of_same_tenant(self):
        ok, conn = run(draft_requests.finish, [{"id": 5, "tenant_id": 1}, None], "viralbarato", 5, "completed", 12, None)
        self.assertEqual(ok, "invalid_post")
        self.assertFalse(conn.committed)

    def test_finish_completed_with_valid_post(self):
        ok, conn = run(draft_requests.finish, [{"id": 5, "tenant_id": 1}, {"id": 12}], "viralbarato", 5, "completed", 12, None)
        self.assertEqual(ok, "ok")
        self.assertTrue(conn.committed)


class PendingCountTests(unittest.TestCase):
    def test_counts_claimable_requests_without_changing_state(self):
        count, conn = run(draft_requests.pending_count, [{"n": 2}], "viralbarato")
        self.assertEqual(count, 2)
        self.assertFalse(conn.committed)
        self.assertTrue(conn.closed)
        sql = conn.cur.sql[0]
        self.assertTrue(sql.startswith("SELECT COUNT(*)"))
        self.assertIn("'pending'", sql)
        self.assertIn("claimed_at <", sql)

    def test_empty_queue_is_zero(self):
        count, _ = run(draft_requests.pending_count, [{"n": 0}], "viralbarato")
        self.assertEqual(count, 0)


class DraftRequestEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        for target, value in (("REVIEW_API_TOKEN", "review-secret"), ("CONTENT_API_TOKEN", "test-secret")):
            patcher = patch.object(main, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_panel_enqueue_requires_review_token(self):
        url = "/api/v1/editorial/review/products/77/draft-request"
        self.assertEqual(self.client.post(url).status_code, 401)
        self.assertEqual(self.client.post(url, headers=AUTOMATION).status_code, 401)

    def test_panel_enqueue_unknown_product_is_404(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value=None)):
            response = self.client.post("/api/v1/editorial/review/products/9/draft-request", headers=REVIEW)
        self.assertEqual(response.status_code, 404)

    def test_panel_enqueue_returns_request(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value={"id": 5, "status": "pending", "created": True})):
            response = self.client.post("/api/v1/editorial/review/products/77/draft-request", headers=REVIEW)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")

    def test_panel_list_requires_review_token(self):
        self.assertEqual(self.client.get("/api/v1/editorial/review/products/draft-requests").status_code, 401)

    def test_claim_requires_automation_token(self):
        url = "/api/v1/viralbarato/editorial/draft-requests/claim"
        self.assertEqual(self.client.post(url, headers=REVIEW).status_code, 401)

    def test_pending_requires_automation_token(self):
        url = "/api/v1/viralbarato/editorial/draft-requests/pending"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, headers=REVIEW).status_code, 401)

    def test_pending_only_for_viralbarato(self):
        url = "/api/v1/outro/editorial/draft-requests/pending"
        self.assertEqual(self.client.get(url, headers=AUTOMATION).status_code, 422)

    def test_pending_returns_count(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value=3)):
            response = self.client.get("/api/v1/viralbarato/editorial/draft-requests/pending", headers=AUTOMATION)
        self.assertEqual(response.json(), {"pending": 3})

    def test_claim_returns_null_when_queue_is_empty(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value=None)):
            response = self.client.post("/api/v1/viralbarato/editorial/draft-requests/claim", headers=AUTOMATION)
        self.assertEqual(response.json(), {"request": None})

    def test_claim_returns_request(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value=CLAIMED)):
            response = self.client.post("/api/v1/viralbarato/editorial/draft-requests/claim", headers=AUTOMATION)
        self.assertEqual(response.json()["request"]["external_id"], "MLB3456789012")

    def test_result_validates_status_and_payload(self):
        url = "/api/v1/viralbarato/editorial/draft-requests/5/result"
        self.assertEqual(self.client.post(url, json={"status": "done"}, headers=AUTOMATION).status_code, 422)
        self.assertEqual(self.client.post(url, json={"status": "completed"}, headers=AUTOMATION).status_code, 422)
        self.assertEqual(self.client.post(url, json={"status": "failed"}, headers=AUTOMATION).status_code, 422)

    def test_result_with_foreign_post_is_422(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value="invalid_post")):
            response = self.client.post(
                "/api/v1/viralbarato/editorial/draft-requests/5/result",
                json={"status": "completed", "post_id": 999},
                headers=AUTOMATION,
            )
        self.assertEqual(response.status_code, 422)

    def test_result_unknown_request_is_404(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value="not_running")):
            response = self.client.post(
                "/api/v1/viralbarato/editorial/draft-requests/5/result",
                json={"status": "failed", "error": "fonte indisponivel"},
                headers=AUTOMATION,
            )
        self.assertEqual(response.status_code, 404)

    def test_result_completed(self):
        with patch.object(main, "run_db_task", AsyncMock(return_value="ok")):
            response = self.client.post(
                "/api/v1/viralbarato/editorial/draft-requests/5/result",
                json={"status": "completed", "post_id": 12},
                headers=AUTOMATION,
            )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
