import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import server as app_server  # noqa: E402


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


@pytest.fixture(scope="session")
def base_url():
    httpd = app_server.build_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    # Prime the service so both metric families have samples.
    fetch(base + "/")
    fetch(base + "/work")
    yield base
    httpd.shutdown()


@pytest.fixture(scope="session")
def metrics_text(base_url):
    status, text = fetch(base_url + "/metrics")
    assert status == 200
    return text


@pytest.fixture(scope="session")
def emitted_metrics(metrics_text):
    names = set()
    for line in metrics_text.splitlines():
        if line.startswith("# TYPE "):
            names.add(line.split()[2])
    return names
