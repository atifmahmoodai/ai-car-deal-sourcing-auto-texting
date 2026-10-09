# ScoutDesk · Car Deal Sourcing & Outreach

A professional acquisition workspace for a used-car dealership: authorized listing feeds, explainable price comparisons, a four-stage lead pipeline, and owner-reviewed SMS/CRM dispatch. The public client brief is preserved in [docs/original-brief.md](docs/original-brief.md).

**Status:** implemented. [GitHub Actions](https://github.com/atifmahmoodai/ai-car-deal-sourcing-auto-texting/actions/workflows/verify.yml) records verification for each revision. This is a single-dealership application, not a completed client installation. No live messages have been sent. Actual marketplace feed access, existing CRM choice/mapping, sender registration, permission records and hosting still require client configuration.

## What is built

- A responsive deal desk, individual lead assessments, source health, activity history and a payload review queue.
- Scheduled authorized HTTPS JSON-feed ingestion plus validate → preview → apply uploads, with strict schemas, atomic imports, stable source keys, older-observation protection and revision tracking.
- Transparent rules using approved comparable asking prices: same make/model/trim/currency, year ±1, mileage ±20,000 miles, observations within 60 days, at least three comparables. No invented AI valuations.
- New Lead → Contacted → Negotiation → Acquired, with decision notes, optimistic revision checks and owner-only backwards moves.
- Twilio SMS adapter, owner approval, fresh permission checks at dispatch, one initial attempt per seller phone, signed status/STOP callbacks and provider reconciliation.
- HubSpot deal upsert adapter with a custom unique source key and explicit client pipeline/stage/currency mapping.
- Django authentication, owner/operator separation, CSRF, login throttling (including admin login), output escaping, restricted feed egress, security headers, PostgreSQL deployment and non-root Docker image.

## Try the fictional demonstration

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py collectstatic --noinput
python manage.py runserver 127.0.0.1:8092
```

Open http://127.0.0.1:8092. The demo uses reserved example URLs/numbers and clearly labeled fictional records. `seed_demo` refuses production. It creates no real outreach permission. All outbound integrations default to disabled.

1. Inspect the Toyota example and its comparable evidence.
2. Prepare an SMS draft; the owner reviews its exact body and recipient in Outreach & CRM.
3. Approve the draft. It stays queued while outbound integration is disabled.
4. Record a manual contact/stage change. Old unsent drafts are cancelled; prepare a fresh CRM sync for the new stage.

Owners manage sources, independently reviewed comparables, permission records and user accounts in Owner controls. Create ordinary active users with **staff/superuser unchecked** for acquisition operators. This is one organization's workspace: all operators share its leads. It is not a multitenant SaaS.

## Verification

```sh
python manage.py collectstatic --noinput
python manage.py test scout
python manage.py makemigrations --check --dry-run
```

The suite covers 34 backend scenarios including atomic/repeated imports, schema rejection, stale/conflicting updates, scoring/currency boundaries, permission and role checks, duplicate suppression, uncertain-provider outcomes, signed callbacks, opt-outs, CSRF, throttling and private-network feed rejection. CI runs on native PostgreSQL 17, tests desktop/mobile browser workflows, checks a database restore, audits locked dependencies and builds the non-root container. Provider tests use mocks; they do not certify a client's live accounts.

## Delivery boundaries

- **Listing access:** the collector consumes the documented authorized JSON contract. It does not bypass Facebook/Craigslist/other marketplace restrictions or claim API access that the client has not supplied. Native provider payloads need a reviewed adapter upstream of this contract.
- **Valuation:** median asking prices are a comparison proxy, not completed-sale valuation or guaranteed profit. Title, accident history, inspection, actual fees and resale demand require human diligence. Mixed currencies are never combined.
- **Messaging:** every job needs owner approval. Public seller contact details alone do not enable SMS. Configure actual consent evidence and sender requirements before enabling dispatch. A single initial SMS is supported; follow-up campaigns and marketing sequences are not included.
- **CRM:** HubSpot is the implemented concrete adapter because the brief did not name the existing CRM. Another CRM needs its own verified adapter/mapping. This version creates/updates deal records; it does not create contact associations or ingest inbound CRM changes.
- **Recovery:** uncertain requests are never automatically repeated. The local application cannot promise exactly-once delivery across a remote service; it records the uncertainty and preserves the contact lock.
- **Scale:** run one scheduler replica. Files are limited to 500 listings/2 MB; this release does not provide distributed crawling, feed pagination or multi-region dispatch.

[Deployment & recovery](docs/deployment.md) · [Integration contracts](docs/integrations.md) · [Rules & acceptance](docs/acceptance.md)
