from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
from .models import Source, Comparable, Consent, Suppression

class ConsentForm(forms.ModelForm):
    class Meta:model=Consent;fields=['phone','evidence','granted_at','expires_at','blocked']
    def clean(self):
        data=super().clean();phone=data.get('phone','')
        RegexValidator(r'^\+[1-9][0-9]{7,14}$','Use E.164 format.')(phone)
        if len(data.get('evidence','').strip())<20:raise ValidationError('Record the permission source, scope and date (at least 20 characters).')
        if data.get('expires_at') and data.get('granted_at') and data['expires_at']<=data['granted_at']:raise ValidationError('Expiry must follow the permission date.')
        return data

class OwnerAdmin(admin.ModelAdmin):
    def has_module_permission(self,r):return r.user.is_superuser
    def has_view_permission(self,r,obj=None):return r.user.is_superuser
    def has_add_permission(self,r):return r.user.is_superuser
    def has_change_permission(self,r,obj=None):return r.user.is_superuser
    def has_delete_permission(self,r,obj=None):return False

@admin.register(Source)
class SourceAdmin(OwnerAdmin):
    list_display=['name','enabled','last_success','last_error'];readonly_fields=['last_success','last_error']

@admin.register(Comparable)
class ComparableAdmin(OwnerAdmin):
    list_display=['year','make','model','trim','price_cents','currency','approved'];list_filter=['approved','make','currency']
    def save_model(self,request,obj,form,change):
        if obj.price_cents<=0:raise ValidationError('Price must be positive.')
        super().save_model(request,obj,form,change)

@admin.register(Consent)
class ConsentAdmin(OwnerAdmin):
    form=ConsentForm;list_display=['phone','granted_at','expires_at','blocked'];readonly_fields=['updated_by','updated_at']
    def save_model(self,request,obj,form,change):obj.updated_by=request.user;super().save_model(request,obj,form,change)

@admin.register(Suppression)
class SuppressionAdmin(OwnerAdmin):
    list_display=['phone','reason','created_at'];readonly_fields=['phone','reason','created_at']
    def has_add_permission(self,r):return False
    def has_change_permission(self,r,obj=None):return False

admin.site.site_header='ScoutDesk · Owner controls'
admin.site.site_title='ScoutDesk'
admin.site.index_title='Sources, evidence and access'
