import logging
from types import SimpleNamespace

from custom_components.meross_local_cloud.log_redaction import (
    RedactionFilter,
    Redactor,
)

UUID = "24042648935315700804c7ae03aa3c11"
MAC = "AA:BB:CC:DD:EE:FF"
IP = "192.168.1.25"


def test_redacts_identifiers_and_secrets_consistently():
    redactor = Redactor(b"secret")

    text = (
        f"device {UUID} mac {MAC} ip {IP} mail user@example.com "
        f'topic /app/1-abcdef123456/subscribe '
        f'payload {{"messageId":"{UUID}","sign":"0123456789abcdef"}}')
    first = redactor.redact(text)
    second = redactor.redact(text)

    assert first == second
    assert UUID not in first
    assert MAC not in first
    assert IP not in first
    assert "user@example.com" not in first
    assert "abcdef123456" not in first
    assert "0123456789abcdef" not in first
    assert "uuid-" in first and "mac-" in first and "ip-" in first
    assert "app-" in first


def test_keeps_loopback_and_masks_other_ips():
    redactor = Redactor(b"secret")

    assert "127.0.0.1" in redactor.redact("127.0.0.1:2002")
    assert "10.0.0.5" not in redactor.redact("host 10.0.0.5")


def test_filter_redacts_message_arguments():
    redactor = Redactor(b"secret")
    record = logging.LogRecord(
        "custom_components.meross_local_cloud.test", logging.INFO, __file__, 1,
        "device %s on %s", (UUID, IP), None)
    record = SimpleNamespace(
        name=record.name, msg=record.msg, args=record.args)

    RedactionFilter(redactor, only_prefix="").filter(record)

    assert UUID not in record.msg
    assert IP not in str(record.args)
