@echo off
setlocal
rem ======================================================================================================
rem  Copies your data (rates, panels, quotations, bank details) from THIS PC into the new Render database.
rem  Run it from the project folder (the one with manage.py), with the venv active:
rem        tools\load_data_to_render.bat
rem  It asks you to paste ONE address and to type YES.  Everything it sets is forgotten when it ends.
rem ======================================================================================================

if not exist manage.py (
    echo Run this from the project folder, the one that contains manage.py.
    exit /b 1
)

echo.
echo STEP 1 of 5: saving your data from this PC into data.json
set PYTHONUTF8=1
set DJANGO_SETTINGS_MODULE=quotation_pwa.settings
set DATABASE_URL=
py manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e admin.logentry -e sessions -o data.json
if errorlevel 1 (
    echo The data could not be saved. Nothing was sent anywhere.
    exit /b 1
)
for %%F in (data.json) do echo Saved data.json, %%~zF bytes.

echo.
echo STEP 2 of 5: the address of the new database
echo In Render open the database quotation-db, find "External Database URL" and copy it.
set /p DB_URL=Paste it here and press Enter: 
if "%DB_URL%"=="" (
    echo Nothing was pasted. Stopped. Nothing was sent anywhere.
    del data.json
    exit /b 1
)
set "DATABASE_URL=%DB_URL%"
py -c "import os,sys,urllib.parse as u; p=u.urlparse(os.environ['DATABASE_URL']); sys.exit(0 if p.scheme in ('postgres','postgresql') and p.hostname else 1)"
if errorlevel 1 (
    echo That does not look like a database address. It must start with postgresql:// . Stopped.
    del data.json
    exit /b 1
)

echo.
echo STEP 3 of 5: WHICH database will be filled?
py -c "import os,urllib.parse as u; p=u.urlparse(os.environ['DATABASE_URL']); print('     host    :', p.hostname); print('     database:', p.path.lstrip('/'))"
echo.
echo The host must start with the same dpg-... name as the quotation-db page in Render
echo (and as DATABASE_URL in quotation-app, tab Environment).  If you are not sure, stop now.
set /p OK=Type YES in capital letters to continue, anything else stops: 
if not "%OK%"=="YES" (
    echo Stopped. Nothing was sent anywhere.
    del data.json
    exit /b 1
)

echo.
echo STEP 4 of 5: loading your data (this can take a minute)
set DJANGO_SETTINGS_MODULE=quotation_pwa.settings_production
set DJANGO_SECRET_KEY=temporary-key-used-only-by-this-script-0123456789
set DJANGO_ALLOWED_HOSTS=localhost
pip install "psycopg[binary]" -q
py manage.py migrate --noinput
if errorlevel 1 (
    echo migrate FAILED. Copy the last lines above and send them. Nothing was loaded.
    goto cleanup
)
py manage.py loaddata data.json
if errorlevel 1 (
    echo loaddata FAILED. Copy the last 15 lines above and send them.
    goto cleanup
)
echo.
echo DONE: your data is in the new database.

:cleanup
echo.
echo STEP 5 of 5: cleaning up
del data.json
echo data.json deleted (it held customer details).
echo Now remove your IP address from the allow list of quotation-db in Render, and close this window.
endlocal
