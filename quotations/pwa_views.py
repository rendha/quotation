"""
quotations/pwa_views.py - the three small pages that make the app installable:
    /manifest.webmanifest   what the browser reads to install the app
    /sw.js                  the service worker (served from the root so it covers the whole app)
    /offline/               the page shown when there is no internet

None of them needs a login (the browser asks for them before anybody is signed in).
"""
import pathlib

from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse

from . import pwa

SERVICE_WORKER_TEMPLATE = pathlib.Path(__file__).with_name("pwa_files") / "sw.template.js"


@login_not_required
def manifest(request):
    return JsonResponse(pwa.manifest(static, reverse), content_type="application/manifest+json")


@login_not_required
def service_worker(request):
    source = pwa.service_worker_source(SERVICE_WORKER_TEMPLATE.read_text(encoding="utf-8"), static, reverse)
    response = HttpResponse(source, content_type="text/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"              # the browser must always check for a newer worker
    return response


@login_not_required
def offline(request):
    return render(request, "quotations/offline.html")
