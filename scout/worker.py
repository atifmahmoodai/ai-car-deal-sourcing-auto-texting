from datetime import timedelta
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import Outbox, Listing, ContactLock, Suppression
from .services import sms_eligibility, audit
from . import providers


def recover_stalled():
    # Never automatically repeat an attempt whose remote outcome is unknown.
    return Outbox.objects.filter(
        status="sending", started_at__lt=timezone.now() - timedelta(minutes=5)
    ).update(
        status="unknown",
        error="Worker interrupted. Reconcile at provider; do not resend automatically.",
    )


def dispatch_one():
    recover_stalled()
    kinds = [kind for kind in ("sms", "crm") if providers.configured(kind)]
    if not kinds:
        return None
    with transaction.atomic():
        job = (
            Outbox.objects.select_for_update()
            .filter(status="queued", kind__in=kinds)
            .order_by("created_at")
            .first()
        )
        if not job:
            return None
        if not providers.configured(job.kind):
            return None
        listing = Listing.objects.select_for_update().get(pk=job.listing_id)
        if (
            not job.approved_by_id
            or not job.approved_by.is_active
            or not job.approved_by.is_superuser
            or listing.revision != job.revision
            or (job.kind == "sms" and sms_eligibility(listing))
        ):
            job.status = "cancelled"
            job.error = "Listing or outreach permission changed."
            job.save()
            return job.pk
        if job.kind == "sms":
            try:
                with transaction.atomic():
                    ContactLock.objects.create(phone=job.payload["to"], job=job)
            except IntegrityError:
                job.status = "cancelled"
                job.error = "Initial outreach already attempted."
                job.save()
                return job.pk
        if not Outbox.objects.filter(pk=job.pk, status="queued").update(
            status="sending", started_at=timezone.now()
        ):
            return None
        job.status = "sending"
    try:
        provider_id = (
            providers.send_sms(job) if job.kind == "sms" else providers.sync_crm(job)
        )
        status = "accepted" if job.kind == "sms" else "synced"
        error = ""
    except providers.Rejected as exc:
        provider_id = ""
        status = "rejected"
        error = "Provider rejected request: " + exc.code
        if job.kind == "sms" and exc.code == "21610":
            Suppression.objects.get_or_create(
                phone=job.payload["to"], defaults={"reason": "Provider opt-out"}
            )
    except Exception:
        provider_id = ""
        status = "unknown"
        error = "Remote outcome uncertain. Reconcile at provider; automatic retry is blocked."
    with transaction.atomic():
        current = Outbox.objects.select_for_update().get(pk=job.pk)
        # A signed delivery callback may arrive before the HTTP response.
        if current.status in ("sending", "unknown"):
            current.status = status
            current.error = error
        if provider_id and not current.provider_id:
            current.provider_id = provider_id
        current.finished_at = timezone.now()
        current.save()
        audit(
            None,
            "outbox.result",
            job.pk,
            status=current.status,
            provider_id=current.provider_id,
        )
    return job.pk
