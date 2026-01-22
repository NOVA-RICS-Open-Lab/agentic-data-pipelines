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
    
    ##Deixa de ver todas as AAS sempre que quer ver uma
    @staticmethod
    def get_shell(shell_id: str) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        return AASClient._get_json(f"{Config.AAS_BASE_URL}/shells/{shell_enc}")
    


    @staticmethod
    def get_submodel(shell_id: str, submodel_id: str) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{submodel_enc}"
        return AASClient._get_json(url)
    
    ##To make changes to the AAS
    
    @staticmethod
    def _post_json(url: str, json_data: dict) -> dict:
        """POST helper (create new elements) like _get_json."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        resp = requests.post(url, json=json_data, headers=headers, timeout=10)
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"Non-JSON response: {resp.text[:500]}")
        return resp.json()

    @staticmethod
    def _patch_json(url: str, json_data: any) -> dict:
        """PATCH helper"""
        headers = {
            "Accept": "application/json, application/ld+json; q=0.9",
            "Content-Type": "application/json"
        }
        resp = requests.patch(url, json=json_data, headers=headers, timeout=10)
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"Non-JSON response: {resp.text[:500]}")
        return resp.json()
    
    @staticmethod
    def create_submodel(submodel: dict) -> dict:
        url = f"{Config.AAS_BASE_URL}/submodels"
        return AASClient._post_json(url, submodel)
    
    @staticmethod 
    def link_submodel_to_shell(shell_id: str, submodel_reference: dict) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodel-refs"
        return AASClient._post_json(url, submodel_reference)

    @staticmethod
    def add_submodel_element(shell_id: str, id_short_path: str, element: dict) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{id_short_path}"
        return AASClient._post_json(url, element)

    @staticmethod
    def update_submodel_element_value(shell_id: str, submodel_id: str, id_short_path: str, value: any) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{submodel_enc}/submodel-elements/{id_short_path}/$value"
        return AASClient._patch_json(url, value)

    @staticmethod
    def delete_submodel_element(shell_id: str, submodel_id: str, id_short_path: str) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{submodel_enc}/submodel-elements/{id_short_path}"
        resp = requests.delete(url, headers={"Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"Non-JSON response: {resp.text[:500]}")
        return resp.json()