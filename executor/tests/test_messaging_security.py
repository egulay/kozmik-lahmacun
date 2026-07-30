import pytest

from kozmik_executor.messaging_security import (
    MessageSignatureError,
    unwrap_message,
    wrap_message,
)


def test_signed_kafka_message_round_trip_and_tamper_rejection(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_MESSAGE_SIGNING_KEY", "k" * 64)
    payload = b'{"schemaVersion":"1.0","eventId":"safe"}'
    envelope = wrap_message(payload)

    assert unwrap_message(envelope) == payload

    tampered = envelope.replace(b"safe", b"evil")
    if tampered == envelope:
        tampered = envelope[:-2] + b"x}"
    with pytest.raises(MessageSignatureError):
        unwrap_message(tampered)


def test_kafka_signing_key_is_required(monkeypatch) -> None:
    monkeypatch.delenv("KAFKA_MESSAGE_SIGNING_KEY", raising=False)

    with pytest.raises(MessageSignatureError):
        wrap_message(b"{}")
