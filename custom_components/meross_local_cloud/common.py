import logging
import re
from typing import List

from . import version

_LOGGER = logging.getLogger(__name__)

# Constants
MEROSS_LOCAL_MDNS_API_SERVICE_TYPE = "_meross-api._tcp.local."
MEROSS_LOCAL_MDNS_MQTT_SERVICE_TYPE = "_meross-mqtt._tcp.local."
MEROSS_LOCAL_MDNS_SERVICE_TYPES = [MEROSS_LOCAL_MDNS_API_SERVICE_TYPE, MEROSS_LOCAL_MDNS_MQTT_SERVICE_TYPE]
DOMAIN = "meross_local_cloud"
PROFILE_CATALOG_SIGNAL = f"{DOMAIN}_profile_catalog"
ATTR_CONFIG = "config"
DEVICE_LIST_COORDINATOR = "device_list_coordinator"
MISSING_TRACKER = "missing_device_tracker"
HA_SWITCH = "switch"
HA_LIGHT = "light"
HA_SENSOR = "sensor"
HA_BINARY_SENSOR = "binary_sensor"
HA_COVER = "cover"
HA_CLIMATE = "climate"
HA_FAN = "fan"
HA_HUMIDIFIER = "humidifier"
HA_NUMBER = "number"
HA_BUTTON = "button"
HA_UPDATE = "update"
MEROSS_PLATFORMS = (HA_SWITCH, HA_LIGHT, HA_COVER, HA_SENSOR, HA_BINARY_SENSOR, HA_CLIMATE, HA_FAN, HA_HUMIDIFIER, HA_NUMBER, HA_BUTTON, HA_UPDATE)

CONF_STORED_CREDS = "stored_credentials"
CONF_BROKER_HOST = "broker_host"
CONF_HTTPS_PORT = "https_port"
CONF_MQTT_PORT = "mqtt_port"
CONF_BROKER_HOST = "broker_host"
CONF_OVERRIDE_MQTT_ENDPOINT = "override_mqtt_endpoint"
CONF_HTTP_ENDPOINT = "http_api_endpoint"
CONF_CA_PEM = "broker_ca_pem"
CONF_CA_FINGERPRINT = "broker_ca_fingerprint"
CONF_MFA_CODE = "mfa_code"

CONF_OPT_CUSTOM_USER_AGENT = "custom_user_agent"
BROKER_ADAPTER = "broker_profile_adapter"
SHUTTER_CONFIG_CACHE = "shutter_config_cache"

HTTP_UPDATE_INTERVAL = 120

HTTP_API_RE = re.compile("(http://|https://)?([^:]+)(:([0-9]+))?")

DEFAULT_USER_AGENT = f"MerossHA/{version.MEROSS_INTEGRATION_VERSION}"


def effective_user_agent(value) -> str:
    """Use the version-tracking default unless a real custom value is set."""
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_USER_AGENT
    if value.startswith("MerossHA/"):
        return DEFAULT_USER_AGENT
    return value

def calculate_id(platform: str, uuid: str, channel: int, supplementary_classifiers: List[str] = None) -> str:
    base = "%s:%s:%d" % (platform, uuid, channel)
    if supplementary_classifiers is not None:
        extrastr = ":".join(supplementary_classifiers)
        if extrastr != "":
            extrastr = ":" + extrastr
        return base + extrastr
    return base


def device_internal_id(device_uuid: str,
                       subdevice_id: str = None) -> str:
    """Historical device-registry identifier kept for entity continuity."""
    if subdevice_id is None:
        return f"#BASE:{device_uuid}"
    return f"#BASE:{device_uuid}#SUB:{subdevice_id}"


def notify_error(hass, notification_id, title, message):
    hass.async_create_task(
        hass.services.async_call(
            domain="persistent_notification",
            service="create",
            service_data={
                "title": title,
                "message": message,
                "notification_id": "%s.%s" % (DOMAIN, notification_id),
            },
        )
    )


def log_exception(message: str = None, logger: logging = None):
    if logger is None:
        logger = logging.getLogger(__name__)
    logger.exception("Error occurred: %s", message or "unknown error")
