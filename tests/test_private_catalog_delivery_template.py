from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_private_catalog_delivery_requires_signed_urls_and_oac_only() -> None:
    template = (ROOT / "deploy/aws/private_catalog_delivery_template.yaml").read_text()

    assert "AWS::CloudFront::OriginAccessControl" in template
    assert "AWS::CloudFront::KeyGroup" in template
    assert "AWS::KMS::Key" in template
    assert "CatalogDeliveryBucket" in template
    assert "TrustedPublicKeyId" in template
    assert "AWS::CloudFront::PublicKey" not in template
    assert "TrustedKeyGroups: [!Ref CatalogKeyGroup]" in template
    assert "ViewerProtocolPolicy: https-only" in template
    assert "s3:GetObject" in template
    assert "release-catalogs/v1/*" in template
    assert "s3:PutObject" not in template
    assert "kms:Decrypt" in template
    assert "AWS:SourceArn" in template
    assert "CloudFrontWebAclArn" in template
    assert "WebACLId: !Ref CloudFrontWebAclArn" in template


def test_private_catalog_delivery_script_requires_explicit_authorization() -> None:
    script = (ROOT / "deploy/aws/deploy_private_catalog_delivery.sh").read_text()

    assert "QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_DEPLOY" in script
    assert "CATALOG_PUBLIC_KEY_ID" in script
    assert "CLOUDFRONT_WAF_WEB_ACL_ARN" in script
    assert "CATALOG_BUCKET_NAME" not in script


def test_private_catalog_sync_is_explicit_and_never_deletes_versions() -> None:
    script = (ROOT / "deploy" / "aws" / "sync_private_catalog_delivery.sh").read_text()

    assert "QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_SYNC" in script
    assert "--sse aws:kms" in script
    assert "--delete" not in script


def test_private_catalog_key_creation_keeps_pem_out_of_cloudformation_parameters() -> None:
    script = (ROOT / "deploy" / "aws" / "create_private_catalog_public_key.sh").read_text()

    assert "QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_KEY_CREATE" in script
    assert "create-public-key" in script
    assert "--rawfile key" in script
