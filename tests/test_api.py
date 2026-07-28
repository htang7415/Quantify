from __future__ import annotations

from fastapi.testclient import TestClient

from quantify.api import VerifyRequest, create_app


class FixtureService:
    def verify(self, *, cik: str, request: VerifyRequest) -> dict:
        return {
            "claim_results": [], "unclassified_statements": [], "non_factual_statements": [],
            "review_items": [], "counterevidence_detail": [], "material_omissions": [],
            "temporal_persistence": [],
            "evidence_scope": {"source": "SEC EDGAR", "forms": list(request.forms), "entity_level_only": True},
            "audit_manifest": {"cik": cik, "as_of_date": request.as_of_date.isoformat()},
        }


def test_v1_verify_endpoint_preserves_contract_inputs() -> None:
    client = TestClient(create_app(FixtureService()))
    response = client.post("/v1/companies/789019/verify", json={
        "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30", "forms": ["10-K"],
    })

    assert response.status_code == 200
    assert response.json()["audit_manifest"] == {"cik": "789019", "as_of_date": "2024-07-30"}
    assert response.json()["evidence_scope"]["forms"] == ["10-K"]
