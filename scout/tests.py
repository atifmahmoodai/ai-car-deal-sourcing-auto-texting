import json
from urllib.parse import urlencode
from datetime import timedelta
from unittest.mock import patch, Mock
from django.test import TestCase,Client,override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from twilio.request_validator import RequestValidator
from .models import Source,Listing,Comparable,Consent,Outbox,ContactLock,Suppression,Audit
from .services import normalize,stage_import,apply_import,score,queue_job,approve_job,change_stage,RuleError
from .worker import dispatch_one,recover_stalled
from .network import fetch_feed
from . import providers

class ScoutTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('owner',password='Fictional-password-2026')
        self.operator=get_user_model().objects.create_user('operator',password='Fictional-password-2026')
        self.source=Source.objects.create(name='Approved test feed',authority='Fictional test data; no real sellers.')
        self.now=timezone.now()
        self.row={'external_id':'L1','url':'https://example.invalid/listing/1','year':2022,'make':'Toyota','model':'Camry','trim':'SE','vin':'','mileage':40000,'price_cents':1800000,'currency':'USD','condition':'good','details':'Fictional listing','seller_phone':'+12025550101','observed_at':self.now.isoformat(),'active':True}
        self.batch=stage_import(self.source,self.raw(),self.owner);apply_import(self.batch.pk,self.owner)
        self.listing=Listing.objects.get()
        for n,p in enumerate([2400000,2450000,2500000]):
            Comparable.objects.create(year=2022,make='Toyota',model='Camry',trim='SE',mileage=40000+n*1000,price_cents=p,currency='USD',source_url=f'https://example.invalid/comp/{n}',observed_at=self.now,approved=True)
        Consent.objects.create(phone=self.row['seller_phone'],evidence='Fictional opt-in, recorded for tests only.',granted_at=self.now-timedelta(days=1),expires_at=self.now+timedelta(days=1),updated_by=self.owner)
    def raw(self,**changes):return json.dumps({'listings':[dict(self.row,**changes)]}).encode()
    def queued(self,kind='sms'):
        job=queue_job(self.listing.pk,kind,self.owner);approve_job(job.pk,self.owner);return job

    def test_import_reapply_does_not_duplicate(self):
        self.assertEqual(apply_import(self.batch.pk,self.owner),0);self.assertEqual(Listing.objects.count(),1)
    def test_batch_all_or_nothing(self):
        bad=dict(self.row,external_id='L2',price_cents=-1)
        with self.assertRaises(RuleError):stage_import(self.source,json.dumps({'listings':[self.row,bad]}).encode(),self.owner)
        self.assertEqual(Listing.objects.count(),1)
    def test_strict_contract(self):
        for changes in [{'price_cents':True},{'price_cents':12.2},{'url':'javascript:alert(1)'},{'seller_phone':'123'},{'observed_at':'2026-99-99T00:00:00Z'},{'observed_at':'2026-01-01'},{'make':'\ud800'},{'vin':'I'*17}]:
            with self.subTest(changes=changes),self.assertRaises(RuleError):normalize(self.raw(**changes))
    def test_same_timestamp_conflict_and_old_update(self):
        b=stage_import(self.source,self.raw(price_cents=1700000),self.owner)
        with self.assertRaises(RuleError):apply_import(b.pk,self.owner)
        b=stage_import(self.source,self.raw(price_cents=1700000,observed_at=(self.now-timedelta(days=1)).isoformat()),self.owner)
        apply_import(b.pk,self.owner);self.listing.refresh_from_db();self.assertEqual(self.listing.price_cents,1800000)
    def test_material_change_invalidates_outreach(self):
        job=self.queued();b=stage_import(self.source,self.raw(price_cents=1900000,observed_at=(self.now+timedelta(seconds=1)).isoformat()),self.owner)
        apply_import(b.pk,self.owner);job.refresh_from_db();self.listing.refresh_from_db()
        self.assertEqual(job.status,'cancelled');self.assertEqual(self.listing.revision,2)
    def test_score_and_currency_isolation(self):
        result=score(self.listing);self.assertEqual(result['median'],24500);self.assertEqual(result['spread'],4500);self.assertTrue(result['eligible'])
        Comparable.objects.all().update(currency='CAD');self.assertIsNone(score(self.listing)['score'])
    def test_comparable_age_and_count(self):
        Comparable.objects.first().delete();self.assertFalse(score(self.listing)['eligible'])
        Comparable.objects.update(observed_at=self.now-timedelta(days=61));self.assertEqual(score(self.listing)['count'],0)
    def test_stale_condition_and_duplicate_vin_hold(self):
        self.listing.observed_at=self.now-timedelta(days=4);self.listing.condition='unknown';self.listing.save()
        self.assertGreaterEqual(len(score(self.listing)['reasons']),2)
        self.listing.vin='1HGCM82633A004352';self.listing.save()
        other=dict(self.row,external_id='L2',vin=self.listing.vin)
        apply_import(stage_import(self.source,json.dumps({'listings':[other]}).encode(),self.owner).pk,self.owner)
        self.assertIn('VIN appears in another active listing',score(self.listing)['reasons'])
    def test_no_consent_or_optout_blocks_draft(self):
        Consent.objects.update(blocked=True)
        with self.assertRaises(RuleError):queue_job(self.listing.pk,'sms',self.owner)
        Consent.objects.update(blocked=False);Suppression.objects.create(phone=self.listing.seller_phone,reason='Test STOP')
        with self.assertRaises(RuleError):queue_job(self.listing.pk,'sms',self.owner)
    def test_owner_approval_and_duplicate_draft(self):
        a=queue_job(self.listing.pk,'sms',self.operator);b=queue_job(self.listing.pk,'sms',self.operator);self.assertEqual(a.pk,b.pk)
        with self.assertRaises(RuleError):approve_job(a.pk,self.operator)
        approve_job(a.pk,self.owner);a.refresh_from_db();self.assertEqual(a.status,'queued')
    def test_worker_disabled_never_calls_provider(self):
        self.queued()
        with patch('scout.providers.send_sms') as send:self.assertIsNone(dispatch_one());send.assert_not_called()
    @patch('scout.providers.configured',return_value=True)
    @patch('scout.providers.send_sms',return_value='SM'+'a'*32)
    def test_dispatch_exactly_one_attempt(self,send,configured):
        job=self.queued();dispatch_one();dispatch_one();job.refresh_from_db()
        self.assertEqual(job.status,'accepted');send.assert_called_once();self.assertTrue(ContactLock.objects.exists())
    @patch('scout.providers.configured',return_value=True)
    @patch('scout.providers.send_sms',side_effect=TimeoutError)
    def test_uncertain_delivery_is_never_retried(self,send,configured):
        job=self.queued();dispatch_one();dispatch_one();job.refresh_from_db();self.assertEqual(job.status,'unknown');send.assert_called_once()
    @patch('scout.providers.configured',return_value=True)
    @patch('scout.providers.send_sms',side_effect=providers.Rejected('21610'))
    def test_provider_optout_persists(self,send,configured):
        job=self.queued();dispatch_one();job.refresh_from_db();self.assertEqual(job.status,'rejected');self.assertTrue(Suppression.objects.exists())
    @patch('scout.providers.configured',return_value=True)
    @patch('scout.providers.send_sms')
    def test_expired_permission_rechecked_at_dispatch(self,send,configured):
        job=self.queued();Consent.objects.update(expires_at=self.now-timedelta(seconds=1));dispatch_one();job.refresh_from_db();self.assertEqual(job.status,'cancelled');send.assert_not_called()
    @patch('scout.providers.configured',return_value=True)
    @patch('scout.providers.send_sms')
    def test_disabled_approver_cannot_dispatch(self,send,configured):
        job=self.queued();self.owner.is_active=False;self.owner.save();dispatch_one();job.refresh_from_db();self.assertEqual(job.status,'cancelled');send.assert_not_called()
    def test_stalled_worker_becomes_unknown(self):
        job=self.queued();Outbox.objects.filter(pk=job.pk).update(status='sending',started_at=self.now-timedelta(minutes=6));self.assertEqual(recover_stalled(),1);job.refresh_from_db();self.assertEqual(job.status,'unknown')
    def test_stage_revision_conflict_and_audit(self):
        change_stage(self.listing.pk,'contacted',1,'Called seller directly.',self.operator)
        with self.assertRaises(RuleError):change_stage(self.listing.pk,'acquired',1,'Stale update.',self.operator)
        self.assertTrue(Audit.objects.filter(event='lead.stage').exists())
    def test_inflight_listing_is_frozen(self):
        job=self.queued();Outbox.objects.filter(pk=job.pk).update(status='sending',started_at=self.now)
        with self.assertRaises(RuleError):change_stage(self.listing.pk,'contacted',1,'Already contacted.',self.owner)
    def test_http_auth_and_owner_boundaries(self):
        self.assertEqual(self.client.get('/').status_code,302)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/imports/').status_code,302)
        job=queue_job(self.listing.pk,'sms',self.operator)
        self.client.post(f'/outbox/{job.pk}/approve/');job.refresh_from_db();self.assertEqual(job.status,'draft')
    def test_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(f'/leads/{self.listing.pk}/draft/sms/').status_code,403)
    def test_login_rate_limit(self):
        for _ in range(10):self.client.post('/login/',{'username':'missing','password':'bad'})
        self.assertEqual(self.client.post('/login/',{'username':'missing','password':'bad'}).status_code,429)
    def test_dashboard_escapes_listing_content(self):
        self.listing.make='<script>alert(1)</script>';self.listing.save();self.client.force_login(self.owner)
        body=self.client.get('/').content.decode();self.assertNotIn('<script>alert(1)</script>',body);self.assertIn('&lt;script&gt;',body)
    @override_settings(TWILIO_AUTH_TOKEN='fictional-token',TWILIO_ACCOUNT_SID='AC'+'b'*32,TWILIO_FROM='+12025550199',PUBLIC_ORIGIN='https://scout.example.invalid')
    def test_signed_callback_and_monotonic_delivery(self):
        job=self.queued();Outbox.objects.filter(pk=job.pk).update(status='sending',started_at=self.now)
        path=f'/hooks/twilio/status/{job.pk}/';data={'AccountSid':'AC'+'b'*32,'To':self.listing.seller_phone,'From':'+12025550199','MessageSid':'SM'+'a'*32,'MessageStatus':'delivered'}
        self.assertEqual(self.client.post(path,data).status_code,403)
        def post():
            sig=RequestValidator('fictional-token').compute_signature('https://scout.example.invalid'+path,data)
            return self.client.post(path,urlencode(data),content_type='application/x-www-form-urlencoded',HTTP_X_TWILIO_SIGNATURE=sig)
        self.assertEqual(post().status_code,204);data['MessageStatus']='sent';post();job.refresh_from_db();self.assertEqual(job.status,'delivered')
    @override_settings(TWILIO_AUTH_TOKEN='fictional-token',TWILIO_ACCOUNT_SID='AC'+'b'*32,TWILIO_FROM='+12025550199',PUBLIC_ORIGIN='https://scout.example.invalid')
    def test_signed_stop_cancels_queued_sms(self):
        job=self.queued();path='/hooks/twilio/inbound/';data={'AccountSid':'AC'+'b'*32,'To':'+12025550199','From':self.listing.seller_phone,'Body':'STOP'}
        sig=RequestValidator('fictional-token').compute_signature('https://scout.example.invalid'+path,data)
        self.client.post(path,urlencode(data),content_type='application/x-www-form-urlencoded',HTTP_X_TWILIO_SIGNATURE=sig);job.refresh_from_db();self.assertEqual(job.status,'cancelled');self.assertTrue(Suppression.objects.exists())
    @override_settings(FEED_HOSTS={'feed.example.invalid'})
    @patch('scout.network.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))])
    def test_private_feed_dns_rejected(self,dns):
        self.source.url='https://feed.example.invalid/feed'
        with self.assertRaises(RuleError):fetch_feed(self.source)
    def test_unapproved_feed_host_rejected(self):
        self.source.url='https://unapproved.example.invalid/feed'
        with self.assertRaises(RuleError):fetch_feed(self.source)
    @override_settings(HUBSPOT_CURRENCY='USD',HUBSPOT_STAGES={'new':'new-id'},HUBSPOT_PIPELINE='pipeline',HUBSPOT_TOKEN='fictional')
    @patch('scout.providers.requests.post')
    def test_hubspot_upsert_contract(self,post):
        job=queue_job(self.listing.pk,'crm',self.owner);post.return_value=Mock(status_code=200);post.return_value.json.return_value={'status':'COMPLETE','results':[{'id':'123'}]}
        self.assertEqual(providers.sync_crm(job),'123');payload=post.call_args.kwargs['json']['inputs'][0];self.assertEqual(payload['idProperty'],'scout_listing_key');self.assertEqual(payload['properties']['amount'],'18000.00')
