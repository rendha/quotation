1. Copy the files over your project.
2. quotations/urls.py - add these two lines inside urlpatterns:
       path("rates/unlock/", views.unlock_rates, name="unlock_rates"),
       path("rates/lock/", views.lock_rates, name="lock_rates"),
3. Render > quotation-app > Environment: add  ADMIN_PASSKEY = (your secret passkey).  Save: Render restarts the app.
   Locally (Command Prompt):  set ADMIN_PASSKEY=yourpasskey   then   python manage.py runserver
4. git add . / git commit / git push, then Manual Deploy.
