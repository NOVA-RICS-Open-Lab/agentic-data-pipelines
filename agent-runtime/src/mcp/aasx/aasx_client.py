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
    def get_submodels_refs(shell_id: str) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        return AASClient._get_json(f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodel-refs")

    @staticmethod
    def get_submodel(shell_id: str, submodel_id: str) -> dict:
        shell_enc = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{submodel_enc}"
        return AASClient._get_json(url)
    
    @staticmethod
    def get_submodel_standalone(submodel_id: str) -> dict:
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/submodels/{submodel_enc}"
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
    def _patch_json(url: str, json_data: dict) -> dict:
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
    def _put_json(url: str, json_data: dict) -> dict:
        """PUT helper for full replacement."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        resp = requests.put(url, json=json_data, headers=headers, timeout=10)
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"Non-JSON response: {resp.text[:500]}")
        return resp.json()
    

    @staticmethod
    def _delete_json(url: str, json_data: dict = None) -> dict:
        """DELETE helper with optional request body."""
        headers = {"Accept": "application/json"}
        if json_data is not None:
            headers["Content-Type"] = "application/json"
        resp = requests.delete(url, json=json_data, headers=headers, timeout=10)
        resp.raise_for_status()
        
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError(f"Non-JSON response: {resp.text[:500]}")
        return resp.json()
    
    @staticmethod
    def create_submodel(submodel: dict) -> dict:
        """
        Create a new standalone submodel. 
        REQUIRED in submodel dict:
        - id: Full IRI (e.g. 'https://example.com/ids/sm/1234_5678_9012_3456')
        - idShort: string name
        - modelType: "Submodel"
        - kind: "Instance"
        - submodelElements: list of element dicts
        """
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
    def update_submodel_element_value(shell_id: str, submodel_id: str, id_short_path: str, element: dict) -> dict:
        """
        Update a submodel element.
        
        Args:
            shell_id: Full shell IRI (e.g., "https://example.com/ids/sm/0352_1113_7042_6202")
            submodel_id: Full submodel IRI (e.g., "https://example.com/ids/sm/0042_1113_7042_5276")
            id_short_path: Dot-separated path to element (e.g., "HMI.Manufacturer")
            element: Complete element JSON including modelType, idShort, valueType, value or others
        
        Returns:
            Updated element JSON
        """
        shell_enc = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_enc}/submodels/{submodel_enc}/submodel-elements/{id_short_path}"
        return AASClient._patch_json(url, element)

    
    @staticmethod 
    def create_shell(shell_payload: dict) -> dict:
        """
        Creates a new AAS Shell on the server.
        
        Args:
            shell_payload: The complete JSON dictionary for the AAS Shell.
        """
        url = f"{Config.AAS_BASE_URL}/shells"
        return AASClient._post_json(url, shell_payload)
    
    @staticmethod
    def delete_shell(shell_id: str) -> dict:
        """
        Deletes a specific AAS Shell by its identifier.
        
        Args:
            shell_id: Full shell IRI (e.g., "https://example.com/ids/aas/1234")
        """
        shell_encoded = AASClient.aas_id_encode(shell_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_encoded}"
        return AASClient._delete_json(url)


    @staticmethod
    def update_shell(shell_id: str, shell_payload: dict) -> dict:
        """Updates an existing Shell on the AAS server by its ID.


        Args:
            shell_id: The unique identifier of the Shell.
            shell_payload: A dictionary representing the updated Shell content.
            
        """

        shell_encoded = AASClient.aas_id_encode(shell_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_encoded}"
        return AASClient._patch_json(url, shell_payload)
    
    @staticmethod
    def get_submodel_element(submodel_id: str) -> dict:
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/submodels/{submodel_enc}/submodel-elements"
        return AASClient._get_json(url)
    
    @staticmethod
    def get_submodel_element_value(submodel_id: str, id_short_path: str) -> dict:
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/submodels/{submodel_enc}/submodel-elements/{id_short_path}/$value"
        return AASClient._get_json(url)
    
    @staticmethod
    def update_submodel_element(submodel_id: str, id_short_path: str, element: dict) -> dict:
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/submodels/{submodel_enc}/submodel-elements/{id_short_path}"
        return AASClient._put_json(url, element)
    
    @staticmethod
    def delete_submodel(submodel_id: str) -> dict:
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/submodels/{submodel_enc}"
        return AASClient._delete_json(url)
    
    @staticmethod
    def delete_submodel_element(submodel_id: str, id_short_path: str) -> dict:
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/submodels/{submodel_enc}/submodel-elements/{id_short_path}"
        return AASClient._delete_json(url)
    
    @staticmethod
    def delete_submodel_ref_to_shell(shell_id: str, submodel_id: str) -> dict:
        shell_encoded = AASClient.aas_id_encode(shell_id)
        submodel_enc = AASClient.aas_id_encode(submodel_id)
        url = f"{Config.AAS_BASE_URL}/shells/{shell_encoded}/submodel-refs/{submodel_enc}" 
        return AASClient._delete_json(url)