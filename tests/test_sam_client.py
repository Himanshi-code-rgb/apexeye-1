"""
Tests for the SAM service client (ApexEye Vision - Iteration 4).

Concept under test: masks round-trip safely through RLE transport and the
client speaks the Colab service protocol without requiring a live server.
"""

import base64
import unittest

import numpy as np

from src.vision.sam_client import (
    SamServiceClient,
    SamServiceError,
    rle_decode,
    rle_encode,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class TestRle(unittest.TestCase):
    def test_round_trip_all_false(self):
        mask = np.zeros((4, 5), dtype=bool)
        np.testing.assert_array_equal(rle_decode(rle_encode(mask)), mask)

    def test_round_trip_all_true(self):
        mask = np.ones((3, 3), dtype=bool)
        np.testing.assert_array_equal(rle_decode(rle_encode(mask)), mask)

    def test_round_trip_mixed(self):
        rng = np.random.default_rng(42)
        mask = rng.random((20, 30)) > 0.5
        np.testing.assert_array_equal(rle_decode(rle_encode(mask)), mask)

    def test_round_trip_single_pixel_true(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[2, 3] = True
        np.testing.assert_array_equal(rle_decode(rle_encode(mask)), mask)

    def test_malformed_rle_rejected(self):
        with self.assertRaises(SamServiceError):
            rle_decode({"shape": [2, 2], "counts": [1, 1]})
        with self.assertRaises(SamServiceError):
            rle_decode({"counts": [4]})


class TestSamServiceClient(unittest.TestCase):
    def _client_with(self, responder):
        calls = {}

        def transport(url, json=None, headers=None, timeout=None):
            calls["url"] = url
            calls["json"] = json
            calls["headers"] = headers
            return responder(url, json, headers)

        client = SamServiceClient(
            base_url="https://fake.trycloudflare.com",
            api_key="secret",
            transport=transport,
        )
        return client, calls

    def test_segment_decodes_masks(self):
        mask = np.zeros((6, 6), dtype=bool)
        mask[1:3, 1:4] = True

        def responder(url, json, headers):
            if url.endswith("/segment"):
                return FakeResponse(payload={"masks": {"car": rle_encode(mask)}})
            return FakeResponse(payload={})

        client, calls = self._client_with(responder)
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        result = client.segment(image, [{"id": "car", "type": "text", "text": "car"}])

        self.assertIn("car", result)
        np.testing.assert_array_equal(result["car"], mask)
        self.assertEqual(calls["headers"]["X-API-Key"], "secret")

    def test_unauthorized_raises(self):
        def responder(url, json, headers):
            return FakeResponse(status_code=401, text="unauthorized")

        client, _ = self._client_with(responder)
        with self.assertRaises(SamServiceError):
            client.segment(np.zeros((4, 4, 3), dtype=np.uint8), [])

    def test_network_error_raises_service_error(self):
        def boom(*args, **kwargs):
            raise ConnectionError("tunnel down")

        client = SamServiceClient(base_url="https://x", transport=boom)
        with self.assertRaises(SamServiceError):
            client.health()

    def test_empty_masks_raises(self):
        def responder(url, json, headers):
            return FakeResponse(payload={"masks": {}})

        client, _ = self._client_with(responder)
        with self.assertRaises(SamServiceError):
            client.segment(np.zeros((4, 4, 3), dtype=np.uint8), [])

    def test_is_available_false_when_unreachable(self):
        def boom(*args, **kwargs):
            raise ConnectionError("down")

        client = SamServiceClient(base_url="https://x", transport=boom)
        self.assertFalse(client.is_available())


if __name__ == "__main__":
    unittest.main()
