import os

import httpx


class VaultSecretError(RuntimeError):
    """Raised when a required runtime secret cannot be read safely."""


_REQUIRED_EXECUTOR_SECRETS = (
    "INTERNAL_API_KEY",
    "KAFKA_MESSAGE_SIGNING_KEY",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
)


async def load_runtime_secrets_from_vault() -> None:
    """Load executor credentials without exposing them through effective configuration."""
    address = os.getenv("VAULT_ADDR", "").rstrip("/")
    token = os.getenv("VAULT_TOKEN", "")
    path = os.getenv(
        "VAULT_EXECUTOR_SECRET_PATH", "secret/data/kozmik-executor"
    ).lstrip("/")
    if not address or not token:
        raise VaultSecretError(
            "Executor startup requires VAULT_ADDR and a scoped VAULT_TOKEN. "
            "Run start-all.sh to initialize the runtime secrets."
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{address}/v1/{path}",
                headers={"X-Vault-Token": token},
            )
            response.raise_for_status()
            values = response.json()["data"]["data"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exception:
        raise VaultSecretError(
            "Executor runtime secrets are unavailable in Vault. Run start-all.sh "
            "with a valid deployment secret source."
        ) from exception

    missing = [
        name for name in _REQUIRED_EXECUTOR_SECRETS
        if not isinstance(values.get(name), str) or not values[name].strip()
    ]
    if missing:
        raise VaultSecretError(
            f"Vault executor secret is missing required keys: {', '.join(missing)}"
        )
    for name in (*_REQUIRED_EXECUTOR_SECRETS, "OPENAI_COMPATIBLE_API_KEY"):
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            os.environ[name] = value
        elif name == "OPENAI_COMPATIBLE_API_KEY":
            os.environ.pop(name, None)
