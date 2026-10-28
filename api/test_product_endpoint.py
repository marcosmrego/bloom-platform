import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main
from product_registration import MercadoLivreProduct

URL = "/api/v1/viralbarato/editorial/products/mercadolivre"
BODY = {"name": "organizador de cabos", "affiliate_link": "https://meli.la/2AbCdEf"}
AUTH = {"Authorization": "Bearer test-secret"}
PRODUCT = MercadoLivreProduct(
    external_id="MLB3456789012",
    title="Organizador De Cabos Mesa Escritorio",
    price=Decimal("29.90"),
    image_url="https://http2.mlstatic.com/D_1.jpg",
    permalink="https://produto.mercadolivre.com.br/MLB-3456789012-organizador-_JM",
    affiliate_link="https://meli.la/2AbCdEf",
    category_id="MLB1648",
)
SAVED = {"id": 77, "external_id": "MLB3456789012"}


class RegisterMercadoLivreProductEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        patcher = patch.object(main, "CONTENT_API_TOKEN", "test-secret")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_requires_automation_token(self):
        self.assertEqual(self.client.post(URL, json=BODY).status_code, 401)

    def test_only_viralbarato_is_enabled(self):
        response = self.client.post(URL.replace("viralbarato", "mundonoprato"), json=BODY, headers=AUTH)
        self.assertEqual(response.status_code, 422)

    def test_reports_missing_marketplace_credentials(self):
        with patch.object(main, "mercadolivre_runtime", None), patch.dict(
            "os.environ", {}, clear=True
        ):
            response = self.client.post(URL, json=BODY, headers=AUTH)
        self.assertEqual(response.status_code, 503)

    def test_registers_and_returns_saved_product(self):
        with patch.object(main, "get_mercadolivre_runtime", return_value=main.MercadoLivreRuntime(None, None)), patch.object(
            main, "register_mercadolivre_product", AsyncMock(return_value=PRODUCT)
        ) as register, patch.object(main, "run_db_task", AsyncMock(return_value=SAVED)):
            response = self.client.post(URL, json=BODY, headers=AUTH)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["product_id"], 77)
        self.assertEqual(body["external_id"], "MLB3456789012")
        self.assertEqual(body["price"], "29.90")
        self.assertNotIn("affiliate_link", body)
        self.assertEqual(register.await_args.args[:2], ("organizador de cabos", "https://meli.la/2AbCdEf"))

    def test_rejects_short_names(self):
        response = self.client.post(URL, json=dict(BODY, name="ab"), headers=AUTH)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
