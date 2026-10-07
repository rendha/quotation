from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from . import pwa_views

urlpatterns = [
    path("", views.dashboard, name="quotation_dashboard"),
    path("new/", views.create_quotation, name="create_quotation"),
    path("quotation/<int:quotation_id>/",views.quotation_detail,name="quotation_detail"),
    path( "quotation/<int:quotation_id>/pdf",views.quotation_pdf,name="quotation_pdf"),
    path("person/", views.person_dashboard, name="person_dashboard"),
    path("login/", login_not_required(auth_views.LoginView.as_view(
        template_name="quotations/login.html", redirect_authenticated_user=True, next_page="quotation_dashboard")), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("manifest.webmanifest", pwa_views.manifest, name="manifest"),
    path("sw.js", pwa_views.service_worker, name="service_worker"),
    path("offline/", pwa_views.offline, name="offline"),
]