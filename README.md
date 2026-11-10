# Splitkit

A self-hostable A/B testing platform: deterministic user bucketing, event ingestion,
a SQL metric layer, a statistics engine, and a readout dashboard that tells you
whether to ship.

![Experiment readout](docs/images/readout.png)

## What it does

1. **Assign.** A TypeScript SDK (or `POST /v1/assign`) puts each user in a variant by
   hashing their id, so assignment needs no database lookup and the Python server and
   the SDK always agree.
2. **Collect.** Exposures and events arrive in batches. Each event carries a client id, so
   retries can't double count, and the server rejects exposures whose variant doesn't
   match the hash.
3. **Define metrics in YAML.** Conversion rates, per-user means and ratio metrics
   (revenue per session) compile to SQL that runs unchanged on PostgreSQL and DuckDB.
4. **Analyze.** The SQL reduces millions of rows to one row of sums per variant. The
   stats engine then runs the appropriate test, a sample-ratio check, multiple-testing
   correction and a sequential test that stays valid when you check results early.
5. **Decide.** The dashboard leads with a verdict (*Ship treatment*, *Keep control*,
   *No detectable difference*, or *Hold*), backed by a forest plot, a metric table, a
   p-value timeline and the exact SQL behind every number.

## Results on public A/B datasets

| Dataset | Users | Finding |
|---|---:|---|
| [Cookie Cats](https://www.kaggle.com/datasets/yufengsui/mobile-games-ab-testing) (mobile game) | 90,189 | Moving the first gate from level 30 to 40 **lowered 7-day retention by 0.82 pts** (19.0% → 18.2%, p = 0.0016; still significant after Benjamini–Hochberg across 3 metrics). Day-1 retention and rounds played: no detectable change. **Recommendation: keep the gate at 30.** |
| [Udacity landing page](https://www.kaggle.com/datasets/zhangluyuan/ab-testing) | 290,584 | 3,893 rows logged a user on the wrong page and were dropped. After that, **no detectable effect** (−0.16 pts, 95% CI [−0.39, +0.08], p = 0.19). **Recommendation: don't ship the new page.** |
| [Criteo uplift v2.1](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) | 13,979,592 | Uneven 85/15 split passes the sample-ratio check. Visits +27%, conversions +59%. **Full readout in 5.2 s** on a laptop (load 14.3 s). |

Reproduce with `python scripts/run_datasets.py` after downloading the CSVs into `data/raw/`.

## Validating the statistics

Unit tests check every test against `statsmodels` or `scipy`. On top of that, a Monte Carlo
simulator runs whole experiments where the true effect is known (1,000 simulated
experiments per scenario, 5,000 users per arm):

| False-positive rate when there is no real effect | |
|---|---:|
| Fixed-horizon z-test, checked once | **5.2%** (nominal 5%) |
| Same test, checked 10 times and stopped at the first "win" | **20.4%** |
| Always-valid mSPRT p-value, checked after every user | **1.9%** |

Checking a standard test repeatedly quadruples false positives. The sequential test fixes
that, at the cost of needing more data to detect a real effect. The timeline chart (Fig. 2
in the screenshot) makes that trade-off visible: the fixed p-value dips below 0.05
days before the always-valid p-value does.

## Engineering numbers

| | |
|---|---|
| Load test (Locust, 100 clients, 60 s, 4 workers) | **1,344 req/s**, p95 140 ms, 0 errors over ~80k requests |
| Event ingestion | ~30,500 events/s; database row counts matched requests exactly |
| Readout with stale planner statistics (20k users) | 62.6 s → **0.25 s** after rewriting the metric SQL (see below) |
| Tests | 132 Python (95.6% coverage, including Postgres integration), 20 SDK, 22 dashboard |

The load test ran with the server, Postgres and Locust all on one M2 laptop, so treat the
throughput as a lower bound.

## Architecture

```mermaid
flowchart LR
    subgraph Client
      SDK["TypeScript SDK<br/>hash → variant<br/>batched events"]
    end
    subgraph Service["FastAPI service"]
      PUB["public routes<br/>config · assign · exposures · events"]
      ADM["admin routes (X-API-Key)<br/>experiments · results · timeline"]
      DASH["dashboard<br/>(React, same origin)"]
    end
    PG[("PostgreSQL<br/>assignments · events")]
    subgraph Analysis
      MET["YAML metrics → SQL<br/>(Postgres / DuckDB)"]
      STATS["stats engine<br/>z / Welch / delta method<br/>CUPED · SRM · BH · mSPRT"]
    end
    SDK -->|config, exposures, events| PUB --> PG
    DASH --> ADM --> MET --> PG
    MET -->|one row of sums per variant| STATS --> ADM
```

## Statistical methods

| Method | Used for |
|---|---|
| Two-proportion z-test, Welch's t-test | conversion and per-user mean metrics |
| Delta method | ratio metrics where the analysis unit (session) differs from the randomization unit (user) |
| CUPED | variance reduction with a pre-experiment covariate (cut CI width by over 40% in tests) |
| Chi-square sample-ratio check | blocks a readout when the observed split doesn't match the plan |
| Benjamini–Hochberg | false discovery rate across an experiment's metrics |
| Mixture SPRT (mSPRT) | always-valid p-values for checking results at any time |
| Power / MDE | sample size planning before launch |

## Problems worth knowing about

**A query that was fast until the statistics went stale.** The original metric SQL
aggregated each event type in its own subquery and joined them back to the users. After
a bulk load, Postgres hadn't analyzed the new rows and estimated 1 user where there were
20,000. It picked a nested loop that recomputed the denominator aggregate once per user:
about 200 million wasted row comparisons and a 62-second readout. Running `ANALYZE` would
have hidden the problem until the next fresh experiment. Instead, the SQL now makes one
`LEFT JOIN` from users to their events and computes numerator and denominator in a single
pass with `FILTER (WHERE ...)`, which has no expensive plan to fall into. A regression
test loads 8,000 users with autovacuum disabled and fails if the readout takes more than 3 s.

**A prior chosen from the wrong checkpoint.** The sequential test needs a prior scale (τ²)
for plausible effect sizes. Setting it from the first checkpoint's baseline looked
reasonable, but at that point most users hadn't had time to convert. The baseline read
about 3% instead of 10%, and the test became so conservative that it never reached
significance. τ² now comes from the latest baseline, which carries no information about
the treatment effect. A test reproduces the delayed-conversion trap.

**Hashing that has to match across two languages.** Assignment uses FNV-1a applied twice:
a single pass gives correlated buckets for sequential ids like `user-1`, `user-2`. Both
implementations hash UTF-8 bytes (not JavaScript's UTF-16 code units) and are tested
against one shared file of 24 cases, including non-ASCII ids.

## Running it

```bash
# Postgres only (for tests)
docker compose -f infra/docker-compose.yml up -d --wait postgres

# Full stack: API + dashboard on http://127.0.0.1:8080
export SPLITKIT_ADMIN_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
docker compose -f infra/docker-compose.yml --profile app up -d --build --wait

# Demo experiment with 14 days of simulated traffic
SPLITKIT_PG_DSN=postgresql://splitkit:splitkit_local_dev@127.0.0.1:55432/splitkit \
  PYTHONPATH=src python scripts/seed_demo.py
```

Then open http://127.0.0.1:8080 and sign in with the admin key.

### Development

```bash
uv venv && uv pip install -e ".[dev]" ruff
export SPLITKIT_PG_DSN=postgresql://splitkit:splitkit_local_dev@127.0.0.1:55432/splitkit
ruff check src tests scripts && pytest --cov=src

(cd sdk && npm ci && npm test)
(cd dashboard && npm ci && npm test && npm run dev)   # dev server proxies the API on :8000
```

Postgres integration tests skip cleanly when `SPLITKIT_PG_DSN` is unset.

## Layout

```
src/splitkit/
  stats/          tests, CUPED, delta method, SRM, BH, power, mSPRT (pure numpy/scipy)
  metrics/        YAML metric spec + SQL compiler
  api/            FastAPI app, routes, repository, settings, rate limiting
  assignment.py   deterministic bucketing (mirrored in sdk/src/assign.ts)
  analysis.py     readout: SRM → metrics → BH
  timeline.py     cumulative readout with always-valid p-values
  datasets/       loaders for the public datasets
sdk/              TypeScript client SDK (no runtime dependencies)
dashboard/        React + TypeScript + Recharts readout UI
config/metrics/   metric definitions for the public datasets
infra/            Dockerfile, docker-compose
scripts/          dataset readouts, simulation, demo seed, load test
tests/            unit, API, Postgres integration, performance regression
```

## Roadmap

- Cloud deployment (planned: AWS ECS Fargate + RDS)
- A live experiment on a production site through the SDK
- Readouts for experiments with more than two arms (assignment already supports them)
- Versioned schema migrations once there is a deployed schema to migrate
