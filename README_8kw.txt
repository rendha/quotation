1. Copy the files in this zip over your project (same folders).
2. quotations/models.py - in class Quotation, next to panel_quantity_manual, add:

    structure_kw_manual = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

3. python manage.py makemigrations quotations
   python manage.py migrate
4. python manage.py add_8kw_inverter        (adds POLYCAB 8KW 3PH DUAL and 1PH DUAL at Rs 58,300)
5. Push to GitHub, Manual Deploy on Render, then run steps 3 (migrate runs by itself) and 4 in the Render Shell once.
