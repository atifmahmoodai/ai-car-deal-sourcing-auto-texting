import requests
from django.conf import settings

class Rejected(Exception):
    def __init__(self,code):self.code=str(code);super().__init__(self.code)

def configured(kind):
    if not settings.OUTBOUND_ENABLED:return False
    if kind=='sms':return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM and settings.PUBLIC_ORIGIN.startswith('https://') and settings.DEALER_NAME!='Example Dealership')
    return bool(settings.HUBSPOT_TOKEN and settings.HUBSPOT_PIPELINE and all(s in settings.HUBSPOT_STAGES for s in ('new','contacted','negotiation','acquired')))

def send_sms(job):
    r=requests.post(f'https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json',
        auth=(settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN),timeout=(5,20),allow_redirects=False,
        data={'From':settings.TWILIO_FROM,'To':job.payload['to'],'Body':job.payload['body'],
              'StatusCallback':settings.PUBLIC_ORIGIN+f'/hooks/twilio/status/{job.pk}/'})
    if 400<=r.status_code<500:raise Rejected(r.json().get('code',r.status_code))
    if r.status_code!=201:raise RuntimeError('Unknown provider acceptance')
    sid=r.json().get('sid','')
    if not sid.startswith('SM') or len(sid)!=34:raise RuntimeError('Invalid provider acknowledgement')
    return sid

def sync_crm(job):
    # The remote custom unique property must be created and verified before enabling this adapter.
    if job.payload['currency']!=settings.HUBSPOT_CURRENCY:raise Rejected('currency_mapping')
    r=requests.post('https://api.hubapi.com/crm/v3/objects/deals/batch/upsert',
        headers={'Authorization':'Bearer '+settings.HUBSPOT_TOKEN},timeout=(5,20),allow_redirects=False,
        json={'inputs':[{'id':job.payload['key'],'idProperty':'scout_listing_key','properties':{
            'dealname':job.payload['title'],'pipeline':settings.HUBSPOT_PIPELINE,
            'dealstage':settings.HUBSPOT_STAGES[job.payload['stage']],
            'amount':f"{job.payload['price_cents']//100}.{job.payload['price_cents']%100:02d}",
            'description':'Source listing: '+job.payload['url'], 'scout_listing_key':job.payload['key']}}]})
    if 400<=r.status_code<500:raise Rejected('crm_http_'+str(r.status_code))
    if r.status_code!=200:raise RuntimeError('Unknown CRM acceptance')
    result=r.json()
    if result.get('status')!='COMPLETE' or len(result.get('results',[]))!=1 or result.get('errors'):raise RuntimeError('Incomplete CRM acknowledgement')
    return str(result['results'][0]['id'])
