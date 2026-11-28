from custom_components.meross_local_cloud.common import (
    format_host_port,
    split_host_port,
)


def test_ipv4_host_port_round_trip():
    assert format_host_port("10.0.0.5", 2001) == "10.0.0.5:2001"
    assert split_host_port("10.0.0.5:2001") == ("10.0.0.5", "2001")


def test_ipv6_host_port_is_bracketed():
    assert format_host_port("::1", 2001) == "[::1]:2001"
    assert split_host_port("[::1]:2001") == ("::1", "2001")


def test_host_without_port_is_supported():
    assert split_host_port("broker.local") == ("broker.local", "")
    assert split_host_port(None) == ("", "")
