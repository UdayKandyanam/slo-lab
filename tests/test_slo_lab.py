import json
import re
from pathlib import Path

import yaml

from conftest import ROOT, fetch

IDENT = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")


def http_identifiers(expr):
    """Metric names in a PromQL expression that belong to the app.

    App metrics all start with http_, so any identifier starting
    that way must be a metric the service actually emits, or a
    series derived from one (histogram buckets, sums, counts).
    """
    return {name for name in IDENT.findall(expr) if name.startswith("http_")}


def is_emitted(name, emitted):
    if name in emitted:
        return True
    return any(name == base + suffix for base in emitted for suffix in ("_bucket", "_sum", "_count"))


def load_yaml(relative):
    return yaml.safe_load((ROOT / relative).read_text())


def all_rule_exprs(alerts_doc):
    exprs = []
    for group in alerts_doc["groups"]:
        for rule in group["rules"]:
            if "expr" in rule:
                exprs.append(rule)
    return exprs


def dashboard_doc():
    return json.loads((ROOT / "grafana/dashboards/checkout-api-slo.json").read_text())


def test_metrics_expose_both_families(base_url, metrics_text):
    fetch(base_url + "/work")
    assert "# TYPE http_requests_total counter" in metrics_text
    assert "# TYPE http_request_duration_seconds histogram" in metrics_text
    assert "http_request_duration_seconds_bucket" in metrics_text
    assert 'path="/work"' in metrics_text


def test_work_returns_200_normally(base_url):
    fetch(base_url + "/chaos?error_rate=0")
    status, _ = fetch(base_url + "/work")
    assert status == 200


def test_work_returns_5xx_when_chaos_is_high(base_url):
    fetch(base_url + "/chaos?error_rate=1")
    try:
        statuses = {fetch(base_url + "/work")[0] for _ in range(5)}
        assert statuses == {500}
    finally:
        fetch(base_url + "/chaos?error_rate=0")
    status, _ = fetch(base_url + "/work")
    assert status == 200


def test_chaos_endpoint_reports_current_rate(base_url):
    fetch(base_url + "/chaos?error_rate=0.5")
    try:
        status, body = fetch(base_url + "/chaos")
        assert status == 200
        assert json.loads(body)["error_rate"] == 0.5
    finally:
        fetch(base_url + "/chaos?error_rate=0")


def test_slo_yaml_has_documented_values():
    doc = load_yaml("slo/slo.yaml")
    assert doc["service"] == "checkout-api"
    slo = doc["slo"]
    assert slo["target"] == 0.999
    assert slo["target_percent"] == 99.9
    assert slo["window_days"] == 30
    budget = slo["error_budget"]
    assert budget["allowed_failure_fraction"] == 0.001
    assert budget["allowed_downtime_minutes_per_30_days"] == 43.2
    assert "http_requests_total" in slo["sli"]["good_query"]
    assert "http_requests_total" in slo["sli"]["total_query"]


def test_alerts_reference_only_emitted_metrics(emitted_metrics):
    rules = all_rule_exprs(load_yaml("slo/alerts.yaml"))
    assert rules, "no alert rules found"
    joined = " ".join(rule["expr"] for rule in rules)
    assert "http_requests_total" in joined
    for rule in rules:
        for name in http_identifiers(rule["expr"]):
            assert is_emitted(name, emitted_metrics), f"alert references unknown metric {name}"


def test_alert_thresholds_windows_and_severities():
    rules = {rule["alert"]: rule for rule in all_rule_exprs(load_yaml("slo/alerts.yaml"))}
    fast = rules["CheckoutAPIFastBurn"]
    assert "14.4 * 0.001" in fast["expr"]
    assert "[1h]" in fast["expr"] and "[5m]" in fast["expr"]
    assert fast["labels"]["severity"] == "page"
    slow = rules["CheckoutAPISlowBurn"]
    assert "6 * 0.001" in slow["expr"]
    assert "[6h]" in slow["expr"] and "[30m]" in slow["expr"]
    assert slow["labels"]["severity"] == "ticket"


def test_dashboard_parses_and_references_only_emitted_metrics(emitted_metrics):
    doc = dashboard_doc()
    assert doc["title"] == "Checkout API SLO"
    exprs = []
    for panel in doc["panels"]:
        for target in panel.get("targets", []):
            if "expr" in target:
                exprs.append(target["expr"])
    assert exprs, "no panel expressions found"
    joined = " ".join(exprs)
    assert "http_requests_total" in joined
    assert "http_request_duration_seconds_bucket" in joined
    for expr in exprs:
        for name in http_identifiers(expr):
            assert is_emitted(name, emitted_metrics), f"dashboard references unknown metric {name}"


def test_dashboard_has_the_documented_panels():
    titles = {panel["title"] for panel in dashboard_doc()["panels"]}
    expected = {
        "Request rate",
        "Error ratio",
        "Error budget remaining (30 days)",
        "Burn rate (1 hour)",
        "Burn rate (6 hours)",
        "Latency p50 and p95",
    }
    assert expected <= titles


def test_compose_has_the_three_services():
    doc = load_yaml("docker-compose.yml")
    services = doc["services"]
    assert set(services) == {"app", "prometheus", "grafana"}
    assert services["app"]["build"] == "./app"
    assert "prom/prometheus" in services["prometheus"]["image"]
    assert "grafana/grafana" in services["grafana"]["image"]


def test_prometheus_config_scrapes_the_app_and_loads_alerts():
    doc = load_yaml("prometheus/prometheus.yml")
    jobs = {config["job_name"] for config in doc["scrape_configs"]}
    assert "checkout-api" in jobs
    assert any("alerts.yaml" in path for path in doc["rule_files"])
    provisioning = load_yaml("grafana/provisioning/datasources/prometheus.yaml")
    source = provisioning["datasources"][0]
    assert source["type"] == "prometheus"
    assert "prometheus:9090" in source["url"]


def test_root_endpoint_speaks_json(base_url):
    status, body = fetch(base_url + "/")
    assert status == 200
    assert json.loads(body)["service"] == "checkout-api"
