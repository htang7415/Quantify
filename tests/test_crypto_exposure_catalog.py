import json
from pathlib import Path

import pytest

from scripts.build_crypto_exposure_catalog import compile_catalog, load_metadata


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_crypto_exposure_is_derived_only_from_released_13f_rows() -> None:
    investor = load_json("web/src/data/investorCatalog.json")
    assets = load_metadata(ROOT / "scripts/crypto_exposure_metadata.json")

    catalog = compile_catalog(investor, assets)
    bitcoin = next(asset for asset in catalog["assets"] if asset["asset_id"] == "bitcoin")
    ethereum = next(asset for asset in catalog["assets"] if asset["asset_id"] == "ethereum")

    assert catalog["investor_manifest_hash"] == investor["manifest_hash"]
    assert bitcoin["reported_etp_value_usd"] == 2_582_823
    assert bitcoin["reporting_manager_count"] == 1
    assert bitcoin["positions"][0]["manager_slug"] == "coatue-management"
    assert bitcoin["positions"][0]["fund_ticker"] == "IBIT"
    assert ethereum["reported_etp_value_usd"] == 0
    assert ethereum["positions"] == []
    assert all(asset["market_data_status"] == "unavailable" for asset in catalog["assets"])


def test_crypto_exposure_rejects_non_sec_identity_sources(tmp_path: Path) -> None:
    metadata = load_json("scripts/crypto_exposure_metadata.json")
    metadata["assets"][0]["funds"][0]["identity_source_url"] = "https://example.com/ibit"
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="SEC source"):
        load_metadata(path)


def test_crypto_exposure_output_matches_the_compiler() -> None:
    expected = compile_catalog(
        load_json("web/src/data/investorCatalog.json"),
        load_metadata(ROOT / "scripts/crypto_exposure_metadata.json"),
    )
    assert load_json("web/src/data/cryptoExposureCatalog.json") == expected
