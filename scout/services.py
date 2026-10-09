import hashlib, json, re, statistics
from datetime import timedelta
from urllib.parse import urlsplit
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import (
    Listing,
    Comparable,
    ImportBatch,
    Audit,
    Consent,
    Outbox,
    ContactLock,
    Suppression,
)


class RuleError(ValueError):
    pass


def audit(actor, event, reference, **detail):
    Audit.objects.create(
        actor=actor, event=event, reference=str(reference), detail=detail
    )


def normalize(raw):
    if len(raw) > 2 * 1024 * 1024:
        raise RuleError("Use a JSON file under 2 MB.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise RuleError("Use valid UTF-8 JSON.")
    if (
        not isinstance(data, dict)
        or set(data) != {"listings"}
        or not isinstance(data["listings"], list)
        or not 1 <= len(data["listings"]) <= 500
    ):
        raise RuleError("Expected a listings array containing 1–500 records.")
    fields = {
        "external_id",
        "url",
        "year",
        "make",
        "model",
        "trim",
        "vin",
        "mileage",
        "price_cents",
        "currency",
        "condition",
        "details",
        "seller_phone",
        "observed_at",
        "active",
    }
    rows = []
    seen = set()
    now = timezone.now()
    for index, item in enumerate(data["listings"], 1):
        if not isinstance(item, dict) or set(item) != fields:
            raise RuleError(f"Row {index}: use the exact example fields.")
        row = dict(item)
        limits = {
            "external_id": 120,
            "url": 1000,
            "make": 60,
            "model": 80,
            "trim": 80,
            "vin": 17,
            "currency": 3,
            "condition": 20,
            "details": 4000,
            "seller_phone": 18,
            "observed_at": 40,
        }
        for key, limit in limits.items():
            if (
                not isinstance(row[key], str)
                or len(row[key]) > limit
                or any(
                    (ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF
                    for c in row[key]
                )
            ):
                raise RuleError(f"Row {index}: invalid {key}.")
            row[key] = row[key].strip()
        if any(not row[k] for k in ["external_id", "make", "model", "trim"]):
            raise RuleError(f"Row {index}: identity and trim are required.")
        if row["external_id"] in seen:
            raise RuleError("Duplicate source IDs in one batch.")
        seen.add(row["external_id"])
        try:
            u = urlsplit(row["url"])
            port = u.port
        except ValueError:
            raise RuleError("Invalid listing URL.")
        if (
            u.scheme != "https"
            or not u.hostname
            or u.username
            or u.password
            or port not in (None, 443)
        ):
            raise RuleError(
                "Listing URLs must be HTTPS without credentials or alternate ports."
            )
        for key, low, high in [
            ("year", 1980, now.year + 1),
            ("mileage", 0, 2000000),
            ("price_cents", 1, 1000000000),
        ]:
            if type(row[key]) is not int or not low <= row[key] <= high:
                raise RuleError(f"Row {index}: invalid {key}.")
        if row["currency"] not in ("USD", "CAD", "GBP", "EUR", "AUD"):
            raise RuleError(
                "Unsupported currency; no currency conversion is performed."
            )
        if (
            row["condition"] not in ("good", "fair", "poor", "unknown")
            or type(row["active"]) is not bool
        ):
            raise RuleError("Invalid condition/active state.")
        if row["seller_phone"] and not re.fullmatch(
            r"\+[1-9][0-9]{7,14}", row["seller_phone"]
        ):
            raise RuleError("Use E.164 seller phone numbers.")
        row["vin"] = row["vin"].upper()
        if row["vin"] and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", row["vin"]):
            raise RuleError("VIN must contain 17 permitted characters.")
        try:
            observed = parse_datetime(row["observed_at"])
        except ValueError:
            raise RuleError("Invalid observation date.")
        if (
            observed is None
            or timezone.is_naive(observed)
            or observed > now + timedelta(minutes=5)
        ):
            raise RuleError(
                "Use an observed_at timestamp with timezone, not a future time."
            )
        row["observed_at"] = observed.isoformat()
        rows.append(row)
    return rows


def stage_import(source, raw, actor):
    if not source.authority.strip():
        raise RuleError("Record the source authorization/terms before importing.")
    rows = normalize(raw)
    return ImportBatch.objects.create(
        source=source,
        payload=rows,
        digest=hashlib.sha256(raw).hexdigest(),
        created_by=actor,
    )


@transaction.atomic
def apply_import(batch_id, actor):
    batch = (
        ImportBatch.objects.select_for_update()
        .select_related("source")
        .get(pk=batch_id)
    )
    if batch.applied_at:
        return 0
    if batch.created_at < timezone.now() - timedelta(minutes=30):
        raise RuleError("This review expired. Upload again.")
    type(batch.source).objects.select_for_update().get(pk=batch.source_id)
    count = 0
    for row in batch.payload:
        vals = dict(row)
        external = vals.pop("external_id")
        vals["observed_at"] = parse_datetime(vals["observed_at"])
        old = (
            Listing.objects.select_for_update()
            .filter(source=batch.source, external_id=external)
            .first()
        )
        if old:
            if Outbox.objects.filter(listing=old, status="sending").exists():
                raise RuleError(
                    "A provider request is in flight. Retry the import after reconciliation."
                )
            if vals["observed_at"] < old.observed_at:
                continue
            changed = any(
                getattr(old, k) != v for k, v in vals.items() if k != "observed_at"
            )
            if changed and vals["observed_at"] == old.observed_at:
                raise RuleError(
                    "Conflicting data at the same observation time. Correct the source timestamp."
                )
            for key, value in vals.items():
                setattr(old, key, value)
            if changed:
                old.revision += 1
                Outbox.objects.filter(
                    listing=old, status__in=["draft", "queued"]
                ).update(
                    status="cancelled",
                    error="Listing changed; review the current revision.",
                )
            old.save()
        else:
            Listing.objects.create(source=batch.source, external_id=external, **vals)
        count += 1
    batch.applied_at = timezone.now()
    batch.save(update_fields=["applied_at"])
    audit(actor, "import.applied", batch.id, rows=count, digest=batch.digest)
    return count


def score(listing):
    now = timezone.now()
    reasons = []
    comps = list(
        Comparable.objects.filter(
            approved=True,
            year__gte=listing.year - 1,
            year__lte=listing.year + 1,
            make__iexact=listing.make,
            model__iexact=listing.model,
            trim__iexact=listing.trim,
            currency=listing.currency,
            mileage__gte=max(0, listing.mileage - 20000),
            mileage__lte=listing.mileage + 20000,
            observed_at__gte=now - timedelta(days=60),
            observed_at__lte=now,
        )
        .exclude(source_url=listing.url)
        .order_by("-observed_at")[:50]
    )
    if not listing.active:
        reasons.append("Listing withdrawn")
    if listing.observed_at < now - timedelta(hours=72):
        reasons.append("Listing older than 72 hours")
    if listing.condition in ("poor", "unknown"):
        reasons.append("Condition needs inspection")
    if len(comps) < 3:
        reasons.append("At least three approved comparable asking prices needed")
    if (
        listing.vin
        and Listing.objects.filter(vin=listing.vin, active=True)
        .exclude(pk=listing.pk)
        .exists()
    ):
        reasons.append("VIN appears in another active listing")
    median = (
        int(statistics.median(c.price_cents for c in comps))
        if len(comps) >= 3
        else None
    )
    # Fixed conservative reserve is explicit, not a trained valuation or guaranteed profit.
    reserve = 250000 if listing.condition == "fair" else 200000
    spread = (median - listing.price_cents - reserve) if median is not None else None
    number = (
        max(0, min(100, round((median - listing.price_cents) * 400 / median)))
        if median
        else None
    )
    if number is not None and listing.condition == "fair":
        number = max(0, number - 10)
    if spread is not None and spread < 250000:
        reasons.append("Estimated spread after reserve is below 2,500")
    return {
        "score": number,
        "median": median / 100 if median else None,
        "spread": spread / 100 if spread is not None else None,
        "reserve": reserve / 100,
        "count": len(comps),
        "comps": comps,
        "reasons": reasons,
        "eligible": not reasons,
    }


def sms_eligibility(listing):
    result = score(listing)
    reasons = list(result["reasons"])
    if listing.stage != "new":
        reasons.append("Initial outreach is only available for New Lead records")
    consent = Consent.objects.filter(
        phone=listing.seller_phone,
        blocked=False,
        granted_at__lte=timezone.now(),
        expires_at__gt=timezone.now(),
    ).first()
    if not listing.seller_phone or not consent or not consent.evidence.strip():
        reasons.append("Current, recorded SMS permission is required")
    if Suppression.objects.filter(phone=listing.seller_phone).exists():
        reasons.append("Seller has opted out")
    if ContactLock.objects.filter(phone=listing.seller_phone).exists():
        reasons.append("This seller already has an initial outreach attempt")
    return reasons


@transaction.atomic
def queue_job(listing_id, kind, actor):
    from django.conf import settings

    listing = Listing.objects.select_for_update().get(pk=listing_id)
    if kind not in ("sms", "crm"):
        raise RuleError("Unknown integration.")
    if kind == "sms":
        reasons = sms_eligibility(listing)
        if reasons:
            raise RuleError("; ".join(reasons))
        body = f"Hello, this is {settings.DEALER_NAME}. Is your {listing.year} {listing.make} {listing.model} still available? Reply STOP to opt out."
        if len(body) > 480:
            raise RuleError("Dealer and vehicle names produce an overly long message.")
        payload = {"to": listing.seller_phone, "body": body}
    else:
        payload = {
            "key": f"{settings.INSTANCE_ID}-{listing.pk}",
            "title": listing.title,
            "stage": listing.stage,
            "price_cents": listing.price_cents,
            "currency": listing.currency,
            "url": listing.url,
            "phone": listing.seller_phone,
        }
    job, created = Outbox.objects.get_or_create(
        listing=listing,
        kind=kind,
        revision=listing.revision,
        defaults={"payload": payload, "created_by": actor, "status": "draft"},
    )
    if created:
        audit(actor, "outbox.drafted", job.id, kind=kind, listing=listing.pk)
    return job


@transaction.atomic
def approve_job(job_id, actor):
    if not actor.is_superuser:
        raise RuleError("Only the owner can approve outbound jobs.")
    job = Outbox.objects.select_for_update().select_related("listing").get(pk=job_id)
    if job.status != "draft":
        raise RuleError("Only a draft can be approved.")
    if job.revision != job.listing.revision:
        raise RuleError("The listing changed; draft its current revision.")
    if job.kind == "sms" and sms_eligibility(job.listing):
        raise RuleError("; ".join(sms_eligibility(job.listing)))
    job.status = "queued"
    job.approved_by = actor
    job.save(update_fields=["status", "approved_by"])
    audit(actor, "outbox.approved", job.id)


@transaction.atomic
def change_stage(listing_id, stage, revision, note, actor):
    listing = Listing.objects.select_for_update().get(pk=listing_id)
    if Outbox.objects.filter(listing=listing, status="sending").exists():
        raise RuleError("An outbound request is in flight; wait for its result.")
    if listing.revision != revision:
        raise RuleError("Another update occurred. Reload this listing.")
    order = [x[0] for x in Listing.STAGES]
    if stage not in order or len(note.strip()) < 5 or len(note) > 1000:
        raise RuleError("Choose a valid stage and record a meaningful note.")
    if not actor.is_superuser and order.index(stage) < order.index(listing.stage):
        raise RuleError("Only the owner can move a lead backwards.")
    old = listing.stage
    listing.stage = stage
    listing.revision += 1
    listing.save()
    Outbox.objects.filter(listing=listing, status__in=["queued", "draft"]).update(
        status="cancelled", error="Lead stage changed; review again."
    )
    audit(actor, "lead.stage", listing.pk, before=old, after=stage, note=note)
