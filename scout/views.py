import hashlib, hmac, json, re
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, F
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from twilio.request_validator import RequestValidator
from .models import Listing, Source, ImportBatch, Outbox, Audit, LoginAttempt, Suppression
from .services import score, sms_eligibility, stage_import, apply_import, queue_job, approve_job, change_stage, RuleError, audit
owner_required=user_passes_test(lambda u:u.is_active and u.is_superuser)

class SignIn(LoginView):
    template_name='scout/login.html'
    def post(self,request,*args,**kwargs):
        data=request.POST.get('username','')[:150]+'|'+request.META.get('REMOTE_ADDR','')
        key=hmac.new(settings.SECRET_KEY.encode(),data.encode(),hashlib.sha256).hexdigest()
        with transaction.atomic():
            attempt,_=LoginAttempt.objects.get_or_create(key=key,defaults={'window':timezone.now()})
            attempt=LoginAttempt.objects.select_for_update().get(pk=attempt.pk)
            if attempt.window<timezone.now()-timedelta(minutes=15):attempt.count=0;attempt.window=timezone.now()
            if attempt.count>=10:return HttpResponse('Too many sign-in attempts. Try again in 15 minutes.',status=429)
            attempt.count+=1;attempt.save()
        response=super().post(request,*args,**kwargs)
        if response.status_code==302:LoginAttempt.objects.filter(key=key).delete()
        return response

@login_required
def dashboard(request):
    query=request.GET.get('q','')[:100];stage=request.GET.get('stage','')
    listings=Listing.objects.filter(active=True).select_related('source').order_by('-observed_at','-id')
    if query:listings=listings.filter(Q(make__icontains=query)|Q(model__icontains=query)|Q(external_id__icontains=query))
    if stage in dict(Listing.STAGES):listings=listings.filter(stage=stage)
    page=Paginator(listings,20).get_page(request.GET.get('page'))
    cards=[{'listing':x,'assessment':score(x)} for x in page]
    return render(request,'scout/dashboard.html',{'cards':cards,'page':page,'q':query,'stage':stage,'stages':Listing.STAGES,
        'active':Listing.objects.filter(active=True).count(),'new':Listing.objects.filter(active=True,stage='new').count(),
        'review':Outbox.objects.filter(status='draft').count(),'uncertain':Outbox.objects.filter(status='unknown').count(),
        'sources':Source.objects.order_by('name'),'outbound':settings.OUTBOUND_ENABLED})

@login_required
def detail(request,pk):
    listing=get_object_or_404(Listing.objects.select_related('source'),pk=pk)
    return render(request,'scout/detail.html',{'listing':listing,'assessment':score(listing),'reasons':sms_eligibility(listing),
        'jobs':listing.outbox_set.order_by('-created_at'),'stages':Listing.STAGES,
        'events':Audit.objects.filter(event='lead.stage',reference=str(pk))[:30]})

@login_required
@require_POST
def stage_view(request,pk):
    try:change_stage(pk,request.POST.get('stage'),int(request.POST.get('revision','0')),request.POST.get('note',''),request.user);messages.success(request,'Lead stage updated. Review a fresh CRM sync when ready.')
    except (RuleError,ValueError) as exc:messages.error(request,str(exc))
    return redirect('detail',pk=pk)

@login_required
@require_POST
def draft_view(request,pk,kind):
    try:queue_job(pk,kind,request.user);messages.success(request,'Draft prepared for owner review. Nothing has been sent.')
    except RuleError as exc:messages.error(request,str(exc))
    return redirect('detail',pk=pk)

@login_required
def outbox(request):
    return render(request,'scout/outbox.html',{'jobs':Paginator(Outbox.objects.select_related('listing','created_by','approved_by').order_by('-created_at'),30).get_page(request.GET.get('page')),'outbound':settings.OUTBOUND_ENABLED})

@owner_required
@require_POST
def approve_view(request,pk):
    try:approve_job(pk,request.user);messages.success(request,'Approved. The worker will dispatch only when integrations are enabled and eligibility still holds.')
    except RuleError as exc:messages.error(request,str(exc))
    return redirect('outbox')

@owner_required
@require_POST
def cancel_view(request,pk):
    if Outbox.objects.filter(pk=pk,status__in=['draft','queued']).update(status='cancelled',error='Cancelled by owner.'):
        audit(request.user,'outbox.cancelled',pk);messages.success(request,'Draft or queued job cancelled.')
    else:messages.error(request,'Already attempted jobs cannot be recalled. Check the provider result.')
    return redirect('outbox')

@owner_required
def import_view(request):
    if request.method=='POST':
        try:
            source=get_object_or_404(Source,pk=request.POST.get('source'))
            upload=request.FILES.get('file')
            if not upload:raise RuleError('Choose a JSON file.')
            batch=stage_import(source,upload.read(2*1024*1024+1),request.user)
            return redirect('review_import',pk=batch.pk)
        except RuleError as exc:messages.error(request,str(exc))
    return render(request,'scout/import.html',{'sources':Source.objects.all()})

@owner_required
def review_import(request,pk):
    batch=get_object_or_404(ImportBatch,pk=pk)
    if request.method=='POST':
        try:count=apply_import(batch.pk,request.user);messages.success(request,f'Applied {count} observations. No outbound messages were sent.');return redirect('dashboard')
        except RuleError as exc:messages.error(request,str(exc))
    return render(request,'scout/review.html',{'batch':batch})

@login_required
def activity(request):
    return render(request,'scout/activity.html',{'events':Paginator(Audit.objects.select_related('actor'),40).get_page(request.GET.get('page'))})

def health(request):return JsonResponse({'status':'ok'})

def signature_ok(request):
    return (settings.TWILIO_AUTH_TOKEN and request.content_type=='application/x-www-form-urlencoded'
        and request.POST.get('AccountSid')==settings.TWILIO_ACCOUNT_SID
        and RequestValidator(settings.TWILIO_AUTH_TOKEN).validate(settings.PUBLIC_ORIGIN+request.get_full_path(),request.POST,request.headers.get('X-Twilio-Signature','')))

@csrf_exempt
@require_POST
def sms_status(request,pk):
    if not signature_ok(request):return HttpResponseForbidden()
    with transaction.atomic():
        job=get_object_or_404(Outbox.objects.select_for_update(),pk=pk,kind='sms')
        sid=request.POST.get('MessageSid','');status=request.POST.get('MessageStatus','')
        if not re.fullmatch(r'SM[0-9a-fA-F]{32}',sid) or request.POST.get('To')!=job.payload.get('to') or request.POST.get('From')!=settings.TWILIO_FROM:return HttpResponseForbidden()
        if job.provider_id and job.provider_id!=sid:return HttpResponseForbidden()
        if job.status not in ('sending','unknown','accepted','sent','delivered','failed','undelivered'):return HttpResponse(status=204)
        rank={'accepted':0,'queued':0,'sending':0,'sent':1,'failed':2,'undelivered':2,'delivered':3}
        if status in rank and rank[status]>=rank.get(job.status,-1):
            job.status='accepted' if rank[status]==0 else status;job.provider_id=sid;job.finished_at=timezone.now();job.save()
        if request.POST.get('ErrorCode')=='21610':Suppression.objects.get_or_create(phone=job.payload['to'],defaults={'reason':'Provider opt-out'})
    return HttpResponse(status=204)

@csrf_exempt
@require_POST
def sms_inbound(request):
    if not signature_ok(request) or request.POST.get('To')!=settings.TWILIO_FROM:return HttpResponseForbidden()
    phone=request.POST.get('From','')
    if re.fullmatch(r'\+[1-9][0-9]{7,14}',phone) and (request.POST.get('OptOutType')=='STOP' or request.POST.get('Body','').strip().upper() in {'STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT'}):
        Suppression.objects.get_or_create(phone=phone,defaults={'reason':'Signed inbound opt-out'})
        # Existing accepted requests cannot be recalled; prevent queued work immediately.
        for job in Outbox.objects.filter(kind='sms',status__in=['draft','queued']):
            if job.payload.get('to')==phone:Outbox.objects.filter(pk=job.pk,status__in=['draft','queued']).update(status='cancelled',error='Seller opted out.')
    # No automatic replies and no automatic START re-enrollment.
    return HttpResponse('<Response/>',content_type='text/xml')
