from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from . import pwa_views, reports

urlpatterns = [
    path("", views.dashboard, name="quotation_dashboard"),
    path("new/", views.create_quotation, name="create_quotation"),
    path("quotation/<int:quotation_id>/",views.quotation_detail,name="quotation_detail"),
    path( "quotation/<int:quotation_id>/pdf",views.quotation_pdf,name="quotation_pdf"),
    path("person/", views.person_dashboard, name="person_dashboard"),
    path("report/", reports.daily_report, name="daily_report"),
    path("login/", login_not_required(auth_views.LoginView.as_view(
        template_name="quotations/login.html", redirect_authenticated_user=True, next_page="quotation_dashboard")), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("manifest.webmanifest", pwa_views.manifest, name="manifest"),
    path("sw.js", pwa_views.service_worker, name="service_worker"),
    path("offline/", pwa_views.offline, name="offline"),
    path("search/", views.search, name="search"),
    path("api/materials/", views.materials_api, name="materials_api"),
    path("api/materials/estimate/", views.materials_estimate, name="materials_estimate"),
    path("quotation/<int:quotation_id>/customer/", views.confirm_customer, name="confirm_customer"),
    path("customer/confirm/", views.confirm_customer, name="confirm_customer_choice"),
    path("quotation/<int:quotation_id>/counted/", views.set_counted, name="set_counted"),
    path("rates/unlock/", views.unlock_rates, name="unlock_rates"),
    path("rates/lock/", views.lock_rates, name="lock_rates"),
    path("pdf/<int:quotation_id>/<str:filename>", views.quotation_pdf, name="quotation_pdf_named"),
    path("view/<int:quotation_id>/<str:filename>", views.quotation_pdf_view, name="quotation_pdf_view"),
]