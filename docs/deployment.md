# Production deployment and recovery

## Bootstrap

Use a dedicated Linux Docker/Compose host and approved DNS hostname. Only Caddy publishes host ports (80/443); PostgreSQL remains on an internal network. PostgreSQL bootstrap creates a non-superuser `scout` role with no database/role creation privileges. Application and scheduler containers run as UID 10001.

1. Copy `.env.example` to `.env`, `chmod 600 .env`. Generate independent random secrets; use hexadecimal database passwords so the DATABASE_URL is correctly encoded. Set SECRET_KEY to at least 50 random characters, the exact approved HTTPS origin/hostname, and real company identity. Generate a permanent INSTANCE_ID with `python -c "import uuid; print(uuid.uuid4())"` and keep it stable across backups/deployments. Keep OUTBOUND_ENABLED=0.
2. `docker compose build`, then `docker compose up -d --wait db`.
3. `docker compose run --rm web python manage.py migrate`.
4. `docker compose run --rm web python manage.py createsuperuser` and choose a strong unique owner password. There is no default account. Use the interactive password validation, not a weak scripted credential.
5. `docker compose run --rm web python manage.py check --deploy`.
6. Start `docker compose up -d`. Caddy obtains HTTPS certificates. TRUST_PROXY is enabled only because the application port is private behind that proxy. Do not publish port 8000 or trust arbitrary forwarding headers.
7. Create named operator accounts with staff/superuser disabled. Verify access. Configure source permissions, feed hosts, comparables and retention. Rehearse with fictional data in an isolated staging installation.
8. Configure sender/CRM mappings and complete acceptance before enabling outbound dispatch. The worker will only process approved jobs for configured providers. Review every existing queued job before switching OUTBOUND_ENABLED to 1.

Use one scheduler replica. It polls enabled feeds every five minutes and processes at most 25 approved jobs every 30 seconds. Queue outages do not silently replay uncertain attempts. Check source last-success/errors and the reconciliation count daily. Application logs omit raw provider bodies and credentials; protect reverse-proxy/server logs and rotate them. Use an approved external monitor for `/health/` plus database/worker checks: the HTTP endpoint is a liveness check, not proof that scheduled work is progressing.

No SMTP is configured. Password recovery is an owner-operated account procedure (`manage.py changepassword`), not an unconfigured email promise. Public registration, MFA/SSO and multitenancy are not included; an approved identity-aware access layer can be added to the deployment if required.

## Backup / restore

Run `bash scripts/backup.sh` to create a consistent PostgreSQL custom-format snapshot and checksum. It contains seller contacts, permission evidence, jobs and audit records: encrypt, restrict and copy off-host according to approved retention. Keep deployment secrets separately in a secret manager. Record source commit and container image digests with each release.

Restore into a **separate, isolated staging database**, never over live data without an approved recovery plan:

1. Verify the dump checksum. Stop staging web/worker; set OUTBOUND_ENABLED=0 and remove sender/CRM/feed secrets from staging.
2. Create an empty target database owned by `scout`. Run `pg_restore --no-owner --exit-on-error -d TARGET_DATABASE SNAPSHOT.dump` with the application role using approved local connection parameters.
3. Run the matching code/migrations. Keep the worker stopped until all restored queued/sending jobs have been reviewed. Historical sending jobs must become unknown and be reconciled against provider evidence before any live cutover.
4. Compare listing/source counts, stages, permission/suppression records, contact locks, outbox statuses and audit totals. Validate owner/operator access and representative screens.
5. Record reviewer, recovery time, recovery point and exceptions. CI checks a synthetic database restore; it does not certify the client's off-host recovery objectives.

For upgrades: take a backup, rehearse on a restored staging copy, stop the scheduler, apply migrations in a maintenance window, then restart web/worker and check queues. Reverting source does not reverse database migrations. Do not roll back contact locks or suppression records without reconciling messages sent after the backup; doing so can permit duplicate outreach.

## Data/security boundaries

All active operators share one dealership's leads and read the activity ledger. Owner screens display seller contact details and control imports/approvals; database administrators remain privileged. Audit records have no application edit/delete surface, but they are not a tamper-proof external ledger. Plan database encryption, least-privilege host access, off-host backup protection and retention with the actual client. Disable inactive users promptly: the dispatcher rechecks the approving owner's active role.
