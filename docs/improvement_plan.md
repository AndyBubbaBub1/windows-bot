# Professionalisation Roadmap for the MOEX Trading Bot

This document summarises the current state of the project, highlights the
highest-impact technical risks discovered during the review, and proposes a
roadmap to bring the bot to a production-ready state.

## Current Observations

- ✅ **Core functionality smoke-tested**: Unit tests and Ruff static checks pass
  locally. The new FIGI helpers fall back gracefully when the Tinkoff Invest SDK
  is unavailable.
- ⚠️ **Risk controls need stronger guarantees**: Portfolio exposure caps relied on
  the price of the currently evaluated instrument, allowing leverage drift when
  instruments have different prices. The fix in this iteration closes that gap.
- ⚠️ **Operational visibility is limited**: There is no unified logging format or
  metrics collection for live trading, making it hard to diagnose production
  issues or monitor strategy health.
- ⚠️ **Configuration is scattered**: Critical runtime settings (tokens, accounts,
  risk limits) are read ad hoc from environment variables or YAML without schema
  validation, increasing the risk of misconfiguration.
- ⚠️ **Deployment path is manual**: No Docker image, IaC scripts, or CI pipeline
  to ship the bot to a controlled environment (e.g. cloud VM, on-prem server).

## Quick Wins (1–2 weeks)

1. **Strengthen automated testing**
   - Add integration tests for the Telegram bot and for fetching FIGI universes
     using a mocked Tinkoff Invest API.
   - Cover critical risk flows (stop-loss triggers, exposure resets at midnight,
     trading halt/resume logic) with property-based tests.

2. **Introduce structured logging and alerting**
   - Use `structlog` or the standard logging module with JSON formatters so logs
     can be indexed by ELK/ClickHouse.
   - Extend `_send_alert` to support multiple channels (e-mail, Slack) and ensure
     alerts are rate-limited.

3. **Formalise configuration**
   - Describe the config schema via `pydantic` or `trafaret` and validate it on
     startup.
   - Support `.env` files and secrets managers to keep tokens out of plain YAML.

4. **Improve observability in tests**
   - Capture metrics via Prometheus-compatible counters for order flow, failed
     executions, and risk-limit breaches.
   - Add assertions in unit tests that metrics are incremented correctly.

## Medium-Term Upgrades (1–2 months)

1. **Refactor strategy lifecycle**
   - Encapsulate strategy state transitions in a finite-state machine to avoid
     side effects inside the event loop.
   - Standardise the interface for calculating signals, risk checks, and order
     submission to make backtesting/live trading interchangeable.

2. **Backtesting parity with live trading**
   - Share a single execution engine between `backtester` and `live_trading` so
     fills, slippage models, and logging behave identically.
   - Persist backtest results to a structured format (Parquet/Feather) and
     generate analytics dashboards automatically.

3. **Deployment automation**
   - Provide Dockerfiles and docker-compose definitions for the bot and its
     dependencies (Redis, PostgreSQL for state, Prometheus/Grafana for metrics).
   - Add GitHub Actions workflows for building images, running integration tests,
     and promoting artefacts to staging/production.

4. **Data management**
   - Introduce a historical data cache (S3/MinIO) with versioning to ensure
     reproducible research.
   - Build data quality checks (schema validation, missing-bars detection)
     executed before every backtest run.

## Long-Term Vision

- **Strategy research platform**: Integrate Jupyter/VS Code devcontainers with
  ready-made datasets and risk primitives so researchers can develop strategies
  in isolation.
- **Plug-in architecture**: Let new strategies register via entry points, and
  enforce contracts with type hints and runtime validation.
- **Continuous monitoring**: Deploy a monitoring stack with anomaly detection for
  PnL, latency, and order rejection rates to catch issues before capital is at
  risk.

## Next Steps

- Prioritise the quick wins and track them as GitHub issues.
- Schedule code reviews focused on risk, execution, and configuration changes.
- Define service-level objectives (SLOs) for latency, uptime, and alert
  response—then design tooling that guarantees these SLOs are met.

By following this roadmap the project will progress towards a professional,
maintainable, and auditable trading system suitable for handling real capital.

