import boto3

from app.config import settings


def get_r2_client():  # type: ignore[no-untyped-def]
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    get_r2_client().put_object(
        Bucket=settings.r2_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_bytes(key: str) -> bytes:
    response = get_r2_client().get_object(Bucket=settings.r2_bucket, Key=key)
    return response["Body"].read()  # type: ignore[no-any-return]
