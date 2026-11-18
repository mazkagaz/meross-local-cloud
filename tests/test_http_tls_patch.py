import meross_iot.http_api as http_api

from custom_components.meross_cloud.common import CONF_HTTP_ENDPOINT
from custom_components.meross_cloud.config_flow import MerossFlowHandler
from custom_components.meross_cloud.patches import set_http_cert_validation
from custom_components.meross_cloud.tls import build_client_ssl_context


async def test_http_client_uses_provided_context(ca_pem):
    original = http_api.ClientSession
    context = build_client_ssl_context(ca_pem, check_hostname=False)
    try:
        set_http_cert_validation(context)
        session = http_api.ClientSession()
        try:
            assert session.connector._ssl is context
        finally:
            await session.close()
    finally:
        http_api.ClientSession = original


def test_setup_schema_has_no_certificate_options():
    handler = MerossFlowHandler()
    keys = {str(key.schema) for key in handler._build_setup_schema().schema}
    assert CONF_HTTP_ENDPOINT in keys
    assert "skip_http_cert_validation" not in keys
    assert "skip_mqtt_cert_validation" not in keys
