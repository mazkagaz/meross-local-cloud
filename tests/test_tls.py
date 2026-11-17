from custom_components.meross_cloud.tls import build_ca_url, write_ca_bundle


def test_build_ca_url_handles_trailing_slash():
    assert build_ca_url("http://10.0.0.5:2003/") == "http://10.0.0.5:2003/ca.crt"
    assert build_ca_url("https://10.0.0.5:2004") == "https://10.0.0.5:2004/ca.crt"


def test_write_ca_bundle(tmp_path):
    path = tmp_path / "broker-ca.pem"
    write_ca_bundle("-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n", str(path))
    assert path.read_text(encoding="utf-8").startswith("-----BEGIN CERTIFICATE-----")
