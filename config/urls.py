from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path
from scout import views
urlpatterns=[path('admin/login/',views.SignIn.as_view()),path('admin/',admin.site.urls),path('login/',views.SignIn.as_view(),name='login'),path('logout/',LogoutView.as_view(),name='logout'),
 path('',views.dashboard,name='dashboard'),path('leads/<int:pk>/',views.detail,name='detail'),path('leads/<int:pk>/stage/',views.stage_view,name='stage'),
 path('leads/<int:pk>/draft/<str:kind>/',views.draft_view,name='draft'),path('outbox/',views.outbox,name='outbox'),
 path('outbox/<uuid:pk>/approve/',views.approve_view,name='approve'),path('outbox/<uuid:pk>/cancel/',views.cancel_view,name='cancel'),
 path('imports/',views.import_view,name='import'),path('imports/<uuid:pk>/',views.review_import,name='review_import'),
 path('activity/',views.activity,name='activity'),path('health/',views.health),
 path('hooks/twilio/status/<uuid:pk>/',views.sms_status),path('hooks/twilio/inbound/',views.sms_inbound)]
