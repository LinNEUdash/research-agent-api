# Research API

[![Test and Deploy](https://github.com/LinNEUdash/research-agent-api/actions/workflows/deploy.yml/badge.svg)](https://github.com/LinNEUdash/research-agent-api/actions/workflows/deploy.yml)

A multi-agent research pipeline exposed as an asynchronous HTTP service and
deployed on AWS.

Give it a question. Three coordinated agents search the web, score every source
they find against a weighted credibility rubric, and return a written report
with confidence levels and a source ranking.

**Live:** https://ja4p86ndhc.us-east-1.awsapprunner.com
**Interactive docs:** https://ja4p86ndhc.us-east-1.awsapprunner.com/docs
**What it produces:** [examples/sample-report.md](examples/sample-report.md) — a
real run, copied from S3 unedited.

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

46 unit tests over the credibility scorer, the redaction layer, the scrape
ceiling, and the API key gate: domain tiers, date handling
(including missing and malformed dates), author and citation factors,
end-to-end scoring for a strong and a weak source, and edge cases such as an
empty URL and a URL with no scheme.

## Deployment

Containerised and running on AWS App Runner from an ECR image, with reports
persisted to S3 through a scoped IAM task role and logs in CloudWatch.

GitHub Actions runs the test suite on every push and, on `main`, builds and
pushes the image to ECR. The deploy job declares `needs: test`, so a failing
suite stops the pipeline before anything is built. App Runner's automatic
deployment picks up the new `:latest` tag and performs a rolling deploy.

To stand it up in a fresh account:

```bash
# 1. Container registry
aws ecr create-repository --repository-name research-agent-api --region us-east-1

# 2. Report bucket, with public access blocked
aws s3api create-bucket --bucket <your-bucket> --region us-east-1
aws s3api put-public-access-block --bucket <your-bucket> \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# 3. Build and push
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker build --platform linux/amd64 -t research-agent-api .
docker tag research-agent-api <account>.dkr.ecr.us-east-1.amazonaws.com/research-agent-api:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/research-agent-api:latest
```

App Runner then needs two distinct roles, which is the step most likely to go
wrong: an **ECR access role** so the service can pull the image, and an
**instance (task) role** the running container assumes. Only the second one
grants S3. The task role used here is scoped to a single prefix:

```json
{
  "Effect": "Allow",
  "Action": ["s3:PutObject", "s3:GetObject"],
  "Resource": "arn:aws:s3:::<your-bucket>/reports/*"
}
```

Runtime configuration is passed as App Runner environment variables:
`GEMINI_API_KEY`, `SERPER_API_KEY`, `LLM_MODEL`, `S3_BUCKET`, `AWS_REGION`,
`API_KEY`, and optionally `MAX_SCRAPE_CHARS` and `LLM_NUM_RETRIES`. Nothing
secret is baked into the image; `.env` is excluded by `.dockerignore`.

Keeping the model name and the quota-related limits in the environment is what
made two of the incidents below one-line recoveries instead of rebuilds.

Build for `linux/amd64` explicitly. App Runner will not run an `arm64` image,
and on an Apple Silicon machine that is the default the build produces.

## Authentication

`POST /research` and both job endpoints require an `X-API-Key` header matching
the `API_KEY` environment variable. `/health` and `/docs` stay open: App Runner
polls `/health` every twenty seconds to decide whether the instance is alive,
and a 401 there would get the container killed and restarted.

When `API_KEY` is unset the check passes, so local runs and CI need no
configuration. The comparison uses `secrets.compare_digest` rather than `==`,
which returns early on the first wrong character and leaks how much of a guess
was right.

This is not about keeping data private; nothing here is secret. It is about the
bill. A run costs fifteen calls against a twenty-per-day quota, so one stranger
who finds the URL can exhaust it for the rest of the day. An open endpoint in
front of a metered upstream hands the invoice to whoever finds it first.

The scheme is declared to FastAPI, so `/docs` renders an Authorize button.

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

**Capping requests did not cap tokens, and the second quota was the one that
bit.**
With `max_rpm=3` holding, a later run still died five minutes in:

```
Quota exceeded for metric:
  generativelanguage.googleapis.com/generate_content_free_tier_input_token_count
  limit: 250000, model: gemini-2.5-flash
```

That limit is measured in input tokens per minute, not calls, so the request
cap has no effect on it. The scraper returned whole pages, boilerplate
included, and the task chain forwards each stage's output to the next as
context, so one long page is paid for three times. Three requests carrying a
few hundred thousand characters clear 250,000 tokens comfortably while sitting
well inside the call limit.

`tools/bounded_scraper.py` puts a ceiling on what a single scrape can
contribute, and says so in the text it returns rather than cutting silently, so
the model reports a partial read instead of mistaking a fragment for the whole
document. The model handle also carries a small retry budget for transient
spikes. Neither is a fix for a quota that stays exhausted, which needs a paid
tier, but the failure mode it was actually hitting is gone.

The general shape: a rate limit is not one number. Check which metric the error
names before deciding what to throttle.

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
- **One run per day on the free tier.** A run makes about fifteen model calls
  and the free tier allows twenty per day, so the second run of any day dies
  partway through with a 429. Raising this is a billing decision, not a code
  one. The number is worth knowing before promising anyone a live demo.
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
