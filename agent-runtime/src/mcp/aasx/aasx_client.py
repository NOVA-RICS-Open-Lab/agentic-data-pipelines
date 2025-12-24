import requests
from src.config.config import Config
import base64


class AASClient:
    """Wrapper to interact with AAS server endpoints."""

    @staticmethod
    def aas_id_encode(iri: str) -> str:
        """Encode an AAS identifier: UTF-8 → Base64 → URL-safe (no padding)."""
        return base64.urlsafe_b64encode(iri.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _get_json(url: str) -> dict:
        """Helper to fetch and parse JSON from a URL."""
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"Non-JSON response: {resp.text[:500]}")
        return resp.json()

    @staticmethod
    def list_shells() -> list[dict]:
        data = AASClient._get_json(f"{Config.AAS_BASE_URL}/shells")
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        if isinstance(data, list):
            return data
        raise RuntimeError(f"Unexpected /shells payload shape: {data}")

    @staticmethod
    def get_submodel(shell_id: str, submodel_id: str) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{submodel_enc}"
        return AASClient._get_json(url)
