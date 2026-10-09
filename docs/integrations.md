# Integration contracts

## Authorized listing sources

An owner records source terms/permission in Source.authority. For scheduled collection set Source.enabled, an HTTPS feed URL and an exact hostname in `FEED_HOSTS`. If authentication is needed, place the token in an environment variable beginning `SCOUT_FEED_` and set Source.token_env to that variable name. Never put credentials in the feed URL. Each request resolves DNS, rejects all non-public addresses, pins the connection to a checked address while retaining TLS hostname verification, blocks redirects and caps responses at 2 MB. No cookies or browser scraping are used.

The feed must return `application/json` with exactly one top-level field, `listings`, containing 1–500 records. Each record has exactly the fields in [the example](../examples/listings.json). Stable `external_id` is unique within the source. Amounts are integer cents; mileage is miles. Supported currencies: USD/CAD/GBP/EUR/AUD. Use timezone-aware observation timestamps; future timestamps beyond five minutes are rejected. Condition: good/fair/poor/unknown. VIN is optional and format-checked, not verified against a vehicle registry. Seller phone is optional E.164. Empty details/phone/VIN are allowed; trim must be explicitly supplied.

Poll with `python manage.py poll_feeds` or the single `run_worker` scheduler. Scheduled sources apply valid observations automatically under the previously approved source contract; manual uploads have a separate preview/apply step. Neither path sends outreach. Missing entries do not imply deletion; withdraw a listing with `active: false`. Older observations are skipped. Different material data at the exact same observation timestamp is rejected. A material change increments the lead revision and cancels its unsent jobs. A source-wide import is transactional and refuses an in-flight provider request; it can be retried once that request settles.

Importer batches store their normalized payload and source hash for traceability. Treat them as personal data, restrict database/backups, and agree retention before loading real sellers. This release has no automated retention/redaction service.

## Twilio

Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, an approved `DEALER_NAME`, HTTPS `PUBLIC_ORIGIN` and `OUTBOUND_ENABLED=1` only after staging acceptance. The sender uses Twilio's Messages API with a status callback URL:

- `POST /hooks/twilio/status/<local-job-uuid>/`
- Configure the sender's incoming message webhook to `POST /hooks/twilio/inbound/`.

The official Twilio SDK validates signatures over the exact configured public URL and every submitted form parameter; account, sender and recipient are checked. Proxy configuration must preserve the external path/query; PUBLIC_ORIGIN must match the Twilio setting. Wrong signatures return 403. Do not rewrite URLs between Twilio and the app.

An owner records the seller's permission source, scope, date and expiry. Do not use demo evidence for real outreach. A worker rechecks permission, opt-outs, listing freshness/revision/stage, score holds and approval authority immediately before attempting a message. A durable per-phone lock prevents multiple first messages across different listings. An in-flight request cannot be recalled if STOP arrives simultaneously; queued work is cancelled and subsequent attempts are blocked.

`accepted` means the API acknowledged the request, not that the seller received it. Signed callbacks track sent/delivered/failed/undelivered and ignore status regressions. STOP and provider error 21610 create a persistent suppression; START does not automatically reenroll. Suppressions cannot be removed through the application. Any future reenrollment process needs separately reviewed evidence and provider-side opt-in handling.

Timeouts, server errors and process interruptions become `unknown`. After five minutes a stalled sending job is held for reconciliation, never put back on the queue. Look up the exact message in Twilio logs, then use the read-only command:

```sh
python manage.py reconcile_job JOB_UUID --message-sid SM_PROVIDER_REFERENCE
```

It checks recipient, sender and exact body before accepting the provider's status. It never sends, removes the contact lock or authorizes another message. If no matching provider record can be established, leave the job held and resolve operationally; do not guess.

## HubSpot

The client must confirm that HubSpot is the intended CRM. Use a least-privilege private app token authorized to read/write deals. Configure the actual `HUBSPOT_PIPELINE`, `HUBSPOT_CURRENCY`, and stage IDs:

```text
HUBSPOT_STAGES=new=ACTUAL_ID,contacted=ACTUAL_ID,negotiation=ACTUAL_ID,acquired=ACTUAL_ID
```

Create a **deal** property named `scout_listing_key`, type `string`, fieldType `text`, with `hasUniqueValue: true`, and a text deal property `scout_seller_phone`. Confirm unique-property support in the client's plan. Do not enable the adapter before validating this schema. The stable key is `<permanent-instance-UUID>-<local-listing-id>`; set INSTANCE_ID once and preserve it, the database and identity across deployments. Never merge unrelated installations into the same remote key namespace.

The adapter uses `POST /crm/v3/objects/deals/batch/upsert` with one input, the unique property and reviewed title, pipeline, stage, asking price, source URL and seller phone. Only a complete acknowledgement with one remote record is marked synced. The configured currency must match the listing; no FX conversion is performed. The mapped deal amount represents **asking price**, not realized sales revenue. Confirm this convention with the CRM owner.

No contact/company associations are created, no external stage is automatically read back, and no CRM record is deleted. Mark uncertain syncs only after reading matching remote evidence with `python manage.py reconcile_job JOB_UUID`. A newer CRM revision should be reviewed after each stage change. External CRM edits can be overwritten by an explicitly approved future sync; establish ownership of these properties during handover.

## Primary API references

- https://www.twilio.com/docs/messaging/api/message-resource
- https://www.twilio.com/docs/usage/webhooks/webhooks-security
- https://www.twilio.com/docs/api/errors/21610
- https://developers.hubspot.com/docs/api-reference/legacy/crm/objects/objects/batch/upsert-objects
- https://developers.hubspot.com/changelog/updating-objects-by-custom-field-and-adding-owner-properties-via-the-api

Consult these and the actual account capabilities before live acceptance; CI uses deterministic provider mocks.
