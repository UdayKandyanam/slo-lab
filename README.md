# SLO Lab

A small, complete SLO setup that runs on a laptop. One sample service, one SLO written in plain language, two burn rate alerts, and a Grafana dashboard that loads itself. I built it to show how I run SLOs as an operating practice: the target, the budget, and the alerts are designed together, and the dashboard is the last step, not the first.

Everything here is invented. The service is called checkout-api, the traffic is synthetic, and no real system is involved.

## The SLO

The full definition lives in [slo/slo.yaml](slo/slo.yaml). The short version:

- Service: checkout-api
- Target: 99.9 percent of requests succeed, over a rolling 30 days
- A request is good when the status is anything other than 5xx. A 4xx means the caller made a mistake and the service answered correctly, so it counts as good.
- The SLI is the ratio of good requests to total requests, computed from the `http_requests_total` counter the service exports.

## The budget math

A 99.9 percent target allows 0.1 percent of requests to fail. In time terms, 30 days hold 43,200 minutes, and 0.1 percent of that is 43.2 minutes of full outage per month. In request terms, a service that takes a million requests in the window may fail one thousand of them. The two views are the same budget, and I find the request view more useful day to day, because most harm arrives as a share of traffic failing, not as the whole service stopping.

The budget is what turns the SLO from a report into a decision tool. While budget remains, shipping is normal. When it is nearly gone, fixing reliability comes first.

## The alerts

[slo/alerts.yaml](slo/alerts.yaml) holds two multi-window burn rate alerts. A burn rate of 1 spends the budget exactly on schedule. Both alerts check a long window and a short window, so they fire on trouble that is real and current, not on a single spike or a stale average.

- Fast burn, severity page: the error ratio over 1 hour and over 5 minutes is above 14.4 times the allowed rate. At that pace the monthly budget is gone in about two days, so it pages a person while there is still budget left to react with.
- Slow burn, severity ticket: the error ratio over 6 hours and over 30 minutes is above 6 times the allowed rate. The budget would last about five days at that pace, so a ticket in working hours is the right response.

## Quick start

You need Docker with Compose.

```sh
docker compose up --build
```

Then, in a second terminal, drive some traffic:

```sh
python3 scripts/drive.py --seconds 30 --rate 20
```

Open Grafana at http://localhost:3030 (login admin, password admin, or just open it, anonymous viewing is on). The "Checkout API SLO" dashboard loads on its own. Prometheus is at http://localhost:3090 and the service itself at http://localhost:3080.

Now break it and watch the burn rates climb:

```sh
curl "http://localhost:3080/chaos?error_rate=0.5"
python3 scripts/drive.py --seconds 45 --rate 20
```

Half of the /work requests now fail. The error ratio panel jumps, the burn rate panels climb past the alert thresholds, and the fast burn alert fires in Prometheus. Set things right again:

```sh
curl "http://localhost:3080/chaos?error_rate=0"
```

## Layout

- `app/` the sample service. Standard library HTTP server plus prometheus_client. Endpoints: `/`, `/work`, `/chaos`, `/metrics`.
- `slo/slo.yaml` the SLO definition, written to be read by people.
- `slo/alerts.yaml` the two burn rate alerts, in Prometheus rule format.
- `prometheus/prometheus.yml` scrape config for the service, with the alerts file loaded as rules.
- `grafana/dashboards/` the "Checkout API SLO" dashboard: request rate, error ratio, error budget remaining, burn rates over 1 hour and 6 hours, latency p50 and p95.
- `grafana/provisioning/` the Prometheus datasource and the dashboard provider, so Grafana configures itself on startup.
- `scripts/drive.py` the traffic driver. It compresses minutes of traffic into seconds, with an optional error rate for the run.
- `docker-compose.yml` wires the three containers together on ports 3080, 3090, and 3030.
- `tests/` pytest checks that need no Docker: the metrics endpoint, the chaos behavior, and cross-checks that the alerts and dashboard only reference metrics the service really emits.

Run the tests with:

```sh
python3 -m venv .venv
.venv/bin/pip install pytest pyyaml prometheus_client
.venv/bin/pytest
```

## Design choices

- One counter and one histogram carry the whole setup. The SLI, both alerts, and four of the six panels come from `http_requests_total` alone. An SLO that needs exotic instrumentation tends to get skipped, so I keep the metric surface small on purpose.
- The SLO is a YAML file a person can read in a review, not a block of PromQL in a wiki. The queries sit next to the target they serve.
- Alerts are written against the raw counters rather than recording rules, so a reviewer can read one file and see the whole path from metric to page. Recording rules are on the roadmap, where they belong after the idea is clear.
- Chaos is a query parameter, not a separate tool. Flipping the failure rate on the service itself keeps the demo honest: the failures flow through the same code path as real ones.
- Grafana is provisioned from files in this repo. Nobody has to click through a setup wizard or import a dashboard by hand.

## Limits

- One service, one SLO. Real estates have many, with dependencies between them, and the interesting fights are about whose budget pays for a shared failure.
- Traffic is synthetic and short. The 30 day budget panel computes remaining budget from a formula over whatever history Prometheus holds, so in a ten minute demo it extrapolates from very little data. The shape is right, the history is not real.
- The burn rate panels use long windows (1 hour, 6 hours, 30 days). Right after startup they move faster than they would in production, because Prometheus rate calculations extrapolate from the few minutes of samples that exist.
- No alert routing. The alerts exist in Prometheus, but nothing here sends the page or files the ticket. Wiring Alertmanager in is easy to say and fiddly to demo well.

## Roadmap

1. A second service with a latency SLO (p95 under a threshold for a share of requests), so the repo shows more than availability.
2. Recording rules for the burn rates, so dashboards and alerts share precomputed series and the queries get shorter.
3. An error budget policy document with freeze rules: what stops shipping when the budget is spent, who can grant an exception, and how the budget earns back.

## License

MIT, see [LICENSE](LICENSE).
