import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from scout.models import Outbox
from scout.services import audit


class Command(BaseCommand):
    help = "Read provider evidence for an uncertain job. Never resends or removes the seller contact lock."

    def add_arguments(self, p):
        p.add_argument("job_id")
        p.add_argument("--message-sid")

    def handle(self, *args, **opts):
        job = Outbox.objects.get(pk=opts["job_id"])
        if job.status not in ("unknown", "accepted", "sent"):
            raise CommandError("Only unresolved/accepted jobs need reconciliation.")
        if job.kind == "sms":
            import re

            sid = opts.get("message_sid") or job.provider_id
            if not sid or not re.fullmatch(r"SM[0-9a-fA-F]{32}", sid):
                raise CommandError(
                    "Supply the SID found in Twilio logs; do not create another message."
                )
            r = requests.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages/{sid}.json",
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                timeout=(5, 20),
                allow_redirects=False,
            )
            r.raise_for_status()
            data = r.json()
            if (
                data.get("to") != job.payload["to"]
                or data.get("from") != settings.TWILIO_FROM
                or data.get("body") != job.payload["body"]
            ):
                raise CommandError(
                    "Provider evidence does not match this exact message."
                )
            status = data.get("status")
            provider_id = sid
            if status in ("queued", "sending"):
                status = "accepted"
            if status not in ("accepted", "sent", "delivered", "failed", "undelivered"):
                raise CommandError("Unrecognized provider status; keep on hold.")
        else:
            r = requests.get(
                f"https://api.hubapi.com/crm/v3/objects/deals/{job.payload['key']}",
                params={
                    "idProperty": "scout_listing_key",
                    "properties": "dealstage,scout_listing_key,amount,pipeline",
                },
                headers={"Authorization": "Bearer " + settings.HUBSPOT_TOKEN},
                timeout=(5, 20),
                allow_redirects=False,
            )
            r.raise_for_status()
            data = r.json()
            props = data.get("properties", {})
            if (
                props.get("scout_listing_key") != job.payload["key"]
                or props.get("pipeline") != settings.HUBSPOT_PIPELINE
                or props.get("dealstage")
                != settings.HUBSPOT_STAGES.get(job.payload["stage"])
            ):
                raise CommandError(
                    "Remote mapping/stage differs; investigate before marking synced."
                )
            provider_id = str(data["id"])
            status = "synced"
        with transaction.atomic():
            current = Outbox.objects.select_for_update().get(pk=job.pk)
            if current.status in ("unknown", "accepted", "sent"):
                current.status = status
                current.provider_id = provider_id
                current.error = ""
                current.finished_at = timezone.now()
                current.save()
                audit(
                    None,
                    "outbox.reconciled",
                    job.pk,
                    status=status,
                    provider_id=provider_id,
                )
        self.stdout.write("Provider evidence reconciled. Nothing was sent.")
