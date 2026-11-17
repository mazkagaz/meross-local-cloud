import aiohttp
import meross_iot.http_api as http_api

from custom_components.meross_cloud.common import CONF_HTTP_SKIP_CERT_VALIDATION
from custom_components.meross_cloud.config_flow import MerossFlowHandler
from custom_components.meross_cloud.patches import (
    _unverified_client_session,
    set_http_cert_validation,
)


def test_http_cert_validation_toggle():
    original = http_api.ClientSession
    try:
        set_http_cert_validation(True)
        assert http_api.ClientSession is _unverified_client_session
        set_http_cert_validation(False)
        assert http_api.ClientSession is aiohttp.ClientSession
    finally:
        http_api.ClientSession = original


def test_setup_schema_exposes_http_certificate_option():
    handler = MerossFlowHandler()
    schema = handler._build_setup_schema()
    keys = {str(key.schema) for key in schema.schema}
    assert CONF_HTTP_SKIP_CERT_VALIDATION in keys
    for key in schema.schema:
        if str(key.schema) == CONF_HTTP_SKIP_CERT_VALIDATION:
            assert key.default() is False
