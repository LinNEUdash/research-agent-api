# Research API

A multi-agent research pipeline exposed as an asynchronous HTTP service and
deployed on AWS.

Give it a question. Three coordinated agents search the web, score every source
they find against a weighted credibility rubric, and return a written report
with confidence levels and a source ranking.

**Live:** _(add your App Runner URL here after Phase 3)_
**Interactive docs:** `<your-url>/docs`

---

## Why it is a job API and not a plain endpoint

A full crew run makes many model and tool calls and takes several minutes. That
is far too long to hold an HTTP connection open, so the service splits the work:

```
POST /research          → 202 Accepted, returns a job_id immediately
GET  /jobs/{id}         → queued | running | done | failed
GET  /jobs/{id}/report  → the finished markdown
```

The crew runs in a background task. Failures are recorded on the job rather
than raised, so a caller polling the job always gets a definite answer.

## Architecture

```
Client
  │  POST /research
  ▼
FastAPI  ──background task──►  Crew (sequential)
  │                              │
  │                              ├─ Researcher   Serper search + page scraping
  │                              ├─ Analyst      credibility scoring
  │                              └─ Controller   final report
  │                                     │
  │                                     ▼
  └────────────────────────────────►  S3  (reports/{job_id}.md)

stdout ──► CloudWatch Logs
```

Each task takes the previous task's output as context. Crew-level memory is
off; that context chain is the only state crossing task boundaries.

## The credibility scorer

A custom CrewAI tool the Analyst calls for every source. Four factors, weighted:

| Factor | Weight | How it is scored |
|---|---|---|
| Domain authority | 40% | Tiered list: `.gov` / `.edu` / journals → 9, established outlets → 7, blog platforms → 4, unranked HTTPS → 5 |
| Content freshness | 25% | ≤90 days → 9, ≤1 year → 7, ≤2 years → 5, older → 3 |
| Citation presence | 20% | Present → 9, absent → 3 |
| Author attribution | 15% | Named author → 8, none → 3 |

**Missing metadata scores 5.0, not 0.** "We could not determine the author" is
not the same claim as "there is no author", and penalising the former would
systematically favour large sites with rich metadata.

### Known limitations

These are in the tool's own docstring and are worth stating plainly:

- Domain-based heuristics only. The scorer does not verify factual accuracy.
- It cannot detect well-crafted misinformation published on a trusted domain.
- Date parsing covers common formats and will miss unusual ones.

The score is a triage signal, not a verdict.

## Running locally

```bash
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash; use bin/activate on macOS/Linux
pip install -r requirements.txt

cp .env.example .env              # then fill in your keys

uvicorn app:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive API docs.

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"query":"latest advances in quantum computing"}'

curl http://localhost:8000/jobs/<job_id>
curl http://localhost:8000/jobs/<job_id>/report
```

## Tests

```bash
python -m pytest tests -q
```

19 unit tests over the credibility scorer: domain tiers, date handling
(including missing and malformed dates), author and citation factors,
end-to-end scoring for a strong and a weak source, and edge cases such as an
empty URL and a URL with no scheme.

## Deployment

Containerised and running on AWS App Runner from an ECR image, with reports
persisted to S3 through a scoped IAM task role and logs in CloudWatch.

GitHub Actions runs the test suite on every push and, on `main`, builds and
pushes the image to ECR. App Runner's automatic deployment picks up the new
`:latest` tag and performs a rolling deploy.

See [RUNBOOK.md](RUNBOOK.md) for the full deployment steps.

## Trade-offs and what is next

Stated plainly because they are real:

- **Job state is in process memory.** It is lost on restart and does not work
  across more than one instance. Next step: DynamoDB.
- **No authentication.** The endpoints are open. Next step: an API key check.
- **IAM is broader than it needs to be.** Started with a permissive policy to
  get the deploy working; it should be narrowed to the single bucket.

## Stack

Python 3.11 · FastAPI · CrewAI · Gemini · Serper · pytest · Docker ·
AWS (ECR, App Runner, S3, CloudWatch) · GitHub Actions
