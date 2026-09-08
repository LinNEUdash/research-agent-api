# Research API

A multi-agent research pipeline exposed as an asynchronous HTTP service and
deployed on AWS.

Give it a question. Three coordinated agents search the web, score every source
they find against a weighted credibility rubric, and return a written report
with confidence levels and a source ranking.

**Live:** https://ja4p86ndhc.us-east-1.awsapprunner.com
**Interactive docs:** https://ja4p86ndhc.us-east-1.awsapprunner.com/docs

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

29 unit tests over the credibility scorer and the redaction layer: domain tiers, date handling
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

## Things that broke, and what they changed

These are the failures from getting the service running, and what each one
changed in the code. They are here because the fixes only make sense next to
the problem that caused them.

**The request cap was set above the provider's actual quota.**
`max_rpm` started at 10. The Gemini free tier allows 5 requests per minute, so
a run would get partway through the research stage and then fail with 429s. The
cap is now 3, taken from the published quota rather than guessed. With it in
place the crew waits for the next minute instead of failing — the run log shows
`Max RPM reached, waiting for next minute to start` where it used to show a
stack trace.

**The provider put the API key in the request URL, so it travelled into places
it should not.**
Gemini authenticates with a `key` query parameter rather than a header, so the
key sits inside the request URL and any HTTP error carries it in the message.
That message was being written to two places that outlive it: the job record
served by `GET /jobs/{id}`, and stdout, which App Runner forwards to CloudWatch.
Anyone who could trigger an error could read the key over HTTP.
`redaction.py` now strips credentials, the job error is redacted before it is
stored rather than before it is displayed, and the log formatter redacts every
record on the way out. Nine tests cover it, using the real 429 as the fixture.

**A hard-coded model was retired underneath the service.**
`gemini-2.0-flash` returned 404 with "this model is no longer available".
Because the model is read from the environment rather than compiled in,
recovering was a one-line change with no redeploy — but the incident is the
argument for keeping it that way, and for having somewhere to fall back to.

**A newer model was not compatible with the pinned client library.**
Switching to the successor the provider recommended produced
`400 Requests ending with a model turn are not supported`: CrewAI, through the
litellm version it pins exactly, assembles a message array the newer model
rejects. Upgrading litellm is not available as a fix because crewai pins it to
one version. Changing models is not just changing a string; the client has to
speak the format the model expects.

**A network call at import time hung the container, and produced no logs to
say so.**
The first App Runner deploy failed health checks with an empty application log
stream — the platform reported the container as unhealthy and nothing else.
Architecture and memory both checked out, which ruled out the usual causes.
Running the same image locally with the production environment variables
reproduced it in two minutes: zero output, indefinitely. The cause was
`boto3.client("s3")` at module scope. With no credentials in the environment
boto3 falls back to the EC2 instance metadata endpoint, which is not reachable
there, and retries until it times out — all before uvicorn binds a port or
logging emits its first record, which is why there was nothing to read. The
client is now built on first use. Anything that touches the network belongs
behind a function, not in module scope.

**A test depended on the day it was run.**
`test_recent_date_scores_high` hard-coded `2026-03-01` and asserted "very
recent". It passed when written and failed six months later once that date aged
past the 90-day band. The freshness tests now build their dates relative to
today.

## Known limits and what is next

- **Job state is in process memory.** It is lost on restart and does not work
  across more than one instance. Next step: DynamoDB.
- **No authentication.** The endpoints are open. Next step: an API key check.
- **CI authenticates with a long-lived access key.** The runtime role is scoped
  to `s3:PutObject`/`s3:GetObject` on `reports/*` in one bucket, but the key
  GitHub Actions uses to push images does not expire and has to be rotated by
  hand. Next step: an OIDC trust policy, so Actions assumes a role per run and
  no static credential exists at all.
- **Redaction is pattern-based.** It catches the credential shapes seen so far.
  A provider using an unfamiliar format would slip through until a pattern is
  added for it.

## Stack

Python 3.11 · FastAPI · CrewAI · Gemini · Serper · pytest · Docker ·
AWS (ECR, App Runner, S3, CloudWatch) · GitHub Actions
