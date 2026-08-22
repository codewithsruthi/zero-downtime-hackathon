# SigNoz dashboard checklist

- [ ] One service: `zero-downtime-factory`
- [ ] Latency: p50/p95 of `factory.run` and `factory.scrape`
- [ ] Throughput: count of `factory.run` per minute
- [ ] Errors: spans with `factory.failure` or non-zero status
- [ ] Heal: count of `factory.heal`
- [ ] Filterable by `factory.component`
- [ ] Import `observability/signoz-dashboard.json`
