import base64
import hashlib
import hmac
import json
import os


class MessageSignatureError(ValueError):
    pass


def _key() -> bytes:
    value = os.getenv("KAFKA_MESSAGE_SIGNING_KEY", "")
    if len(value) < 32:
        raise MessageSignatureError("KAFKA_MESSAGE_SIGNING_KEY_UNAVAILABLE")
    return value.encode()


def wrap_message(payload: bytes) -> bytes:
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(_key(), encoded.encode("ascii"), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return json.dumps(
        {"schemaVersion": "1.0", "payload": encoded, "signature": signature},
        separators=(",", ":"),
    ).encode()


def unwrap_message(envelope: bytes) -> bytes:
    try:
        value = json.loads(envelope)
        encoded = value["payload"]
        supplied = value["signature"]
        if value["schemaVersion"] != "1.0" or not isinstance(encoded, str):
            raise MessageSignatureError("KAFKA_MESSAGE_ENVELOPE_INVALID")
        expected = base64.urlsafe_b64encode(
            hmac.new(_key(), encoded.encode("ascii"), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(expected, supplied):
            raise MessageSignatureError("KAFKA_MESSAGE_SIGNATURE_INVALID")
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except MessageSignatureError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exception:
        raise MessageSignatureError("KAFKA_MESSAGE_ENVELOPE_INVALID") from exception
