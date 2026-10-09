from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from scout.models import Source
from scout.network import fetch_feed
from scout.services import stage_import, apply_import


class Command(BaseCommand):
    help = "Ingest enabled, authorized JSON feeds. Never sends messages."

    def handle(self, *args, **opts):
        owner = (
            get_user_model()
            .objects.filter(is_active=True, is_superuser=True)
            .order_by("id")
            .first()
        )
        if not owner:
            raise CommandError("Create an owner first.")
        for source in Source.objects.filter(enabled=True):
            try:
                batch = stage_import(source, fetch_feed(source), owner)
                apply_import(batch.id, owner)
                source.last_success = timezone.now()
                source.last_error = ""
            except Exception as exc:
                # No feed credentials, response bodies or seller data in logs.
                source.last_error = "Fetch/import failed: " + type(exc).__name__
            source.save(update_fields=["last_success", "last_error"])
            self.stdout.write(
                f"Source {source.pk}: " + (source.last_error or "updated")
            )
