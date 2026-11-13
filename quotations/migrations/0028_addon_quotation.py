import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0027_add_enphase_microinverters"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AddonQuotation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("offer_no", models.CharField(blank=True, max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("customer_name", models.CharField(max_length=200)),
                ("sales_name", models.CharField(blank=True, max_length=200, verbose_name="Quotation for (sales person)")),
                ("location", models.CharField(blank=True, max_length=100)),
                ("validity_days", models.PositiveIntegerField(default=15)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("taxable_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("gst_low_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("gst_high_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("calculated_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("final_override", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("final_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("margin_drop", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Add-on quotation", "ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="AddonItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=300)),
                ("specification", models.TextField(blank=True)),
                ("make", models.CharField(blank=True, max_length=200)),
                ("unit", models.CharField(default="Nos", max_length=50)),
                ("quantity", models.DecimalField(decimal_places=2, default=1, max_digits=10)),
                ("rate", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("gst_percent", models.DecimalField(decimal_places=2, default=18, max_digits=5)),
                ("addon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="quotations.addonquotation")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="quotations.product")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
