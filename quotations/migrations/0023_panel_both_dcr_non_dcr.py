from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quotations', '0022_quotation_is_customer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quotation',
            name='panel_dcr_status',
            field=models.CharField(choices=[('dcr', 'DCR'), ('non_dcr', 'Non-DCR'), ('both', 'DCR + Non-DCR')], default='dcr', max_length=20),
        ),
        migrations.AddField(
            model_name='quotation',
            name='panel2_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='quotations_second_panel', to='quotations.paneloption'),
        ),
        migrations.AddField(
            model_name='quotation',
            name='panel2_quantity',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
