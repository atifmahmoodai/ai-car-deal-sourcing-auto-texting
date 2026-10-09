import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Source(models.Model):
    name = models.CharField(max_length=100, unique=True)
    url = models.URLField(max_length=1000, blank=True)
    token_env = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=False)
    authority = models.TextField(
        help_text="Permission/license or public feed terms reviewed by the owner."
    )
    last_success = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=250, blank=True)

    def __str__(self):
        return self.name


class Listing(models.Model):
    STAGES = [
        ("new", "New Lead"),
        ("contacted", "Contacted"),
        ("negotiation", "Negotiation"),
        ("acquired", "Acquired"),
    ]
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=120)
    url = models.URLField(max_length=1000)
    year = models.PositiveIntegerField()
    make = models.CharField(max_length=60)
    model = models.CharField(max_length=80)
    trim = models.CharField(max_length=80)
    vin = models.CharField(max_length=17, blank=True)
    mileage = models.PositiveIntegerField()
    price_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="USD")
    condition = models.CharField(max_length=20)
    details = models.TextField(blank=True)
    seller_phone = models.CharField(max_length=18, blank=True)
    observed_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    stage = models.CharField(max_length=20, choices=STAGES, default="new")
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="listing_source_key"
            ),
            models.CheckConstraint(
                condition=Q(price_cents__gt=0), name="positive_listing_price"
            ),
        ]
        indexes = [
            models.Index(fields=["make", "model", "year"]),
            models.Index(fields=["stage", "active"]),
        ]

    @property
    def title(self):
        return f"{self.year} {self.make} {self.model} {self.trim}"

    @property
    def price(self):
        return self.price_cents / 100

    def __str__(self):
        return self.title


class Comparable(models.Model):
    year = models.PositiveIntegerField()
    make = models.CharField(max_length=60)
    model = models.CharField(max_length=80)
    trim = models.CharField(max_length=80)
    mileage = models.PositiveIntegerField()
    price_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="USD")
    source_url = models.URLField(max_length=1000, unique=True)
    observed_at = models.DateTimeField()
    approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.year} {self.make} {self.model} — {self.source_url}"


class Consent(models.Model):
    phone = models.CharField(max_length=18, unique=True)
    evidence = models.TextField()
    granted_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    blocked = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    payload = models.JSONField()
    digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True)


class Outbox(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=[("sms", "SMS"), ("crm", "CRM")])
    revision = models.PositiveIntegerField()
    payload = models.JSONField()
    status = models.CharField(max_length=20, default="queued")
    provider_id = models.CharField(max_length=120, blank=True)
    error = models.CharField(max_length=250, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_jobs",
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "kind", "revision"], name="one_outbox_per_revision"
            )
        ]
        indexes = [models.Index(fields=["status", "created_at"])]


class ContactLock(models.Model):
    phone = models.CharField(max_length=18, primary_key=True)
    job = models.OneToOneField(Outbox, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Audit(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True
    )
    event = models.CharField(max_length=80)
    reference = models.CharField(max_length=150)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    window = models.DateTimeField()


class Suppression(models.Model):
    phone = models.CharField(max_length=18, unique=True)
    reason = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
