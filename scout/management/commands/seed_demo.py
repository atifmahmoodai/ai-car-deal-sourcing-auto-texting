import json
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from scout.models import Source,Comparable,Consent
from scout.services import stage_import,apply_import
class Command(BaseCommand):
    help='Create fictional local demonstration data. Refuses production.'
    def handle(self,*args,**opts):
        if settings.PRODUCTION:raise CommandError('Demo data is forbidden in production.')
        owner=get_user_model().objects.filter(is_superuser=True,is_active=True).first()
        if not owner:raise CommandError('Create a local owner with createsuperuser first.')
        source,_=Source.objects.get_or_create(name='Fictional demonstration feed',defaults={'authority':'Synthetic showcase data. Not real listings or seller contacts.'})
        now=timezone.now();rows=[]
        cars=[(2022,'Toyota','Camry','SE',42000,1800000,'good'),(2021,'Honda','Civic','Sport',35000,2200000,'fair'),(2020,'Ford','F-150','XLT',58000,2000000,'unknown')]
        for n,(year,make,model,trim,miles,price,condition) in enumerate(cars,1):
            rows.append({'external_id':f'DEMO-{n}','url':f'https://example.invalid/listings/{n}','year':year,'make':make,'model':model,'trim':trim,'vin':'','mileage':miles,'price_cents':price,'currency':'USD','condition':condition,'details':'Fictional demonstration only. Arrange an inspection and verify title, condition and source rights before any real acquisition.','seller_phone':f'+1202555010{n}','observed_at':now.isoformat(),'active':True})
            for j,amount in enumerate(([2400000,2450000,2500000] if n==1 else [2250000,2300000,2350000] if n==2 else [3000000,3100000,3200000])):
                Comparable.objects.update_or_create(source_url=f'https://example.invalid/comparables/{n}-{j}',defaults={'year':year,'make':make,'model':model,'trim':trim,'mileage':miles+j*1000,'price_cents':amount,'currency':'USD','observed_at':now,'approved':True})
        apply_import(stage_import(source,json.dumps({'listings':rows}).encode(),owner).id,owner)
        Consent.objects.update_or_create(phone='+12025550101',defaults={'evidence':'Fictional demo permission; does not authorize any actual outreach.','granted_at':now-timedelta(days=1),'expires_at':now+timedelta(days=30),'updated_by':owner})
        self.stdout.write('Created fictional listings and comparables. Outbound integrations remain disabled by default.')
