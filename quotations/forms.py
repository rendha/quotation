from django import forms
from .models import Quotation


class QuotationForm(forms.ModelForm):

    class Meta:
        model = Quotation

        fields = [
            "customer_name",
            "customer_phone",
            "customer_address",
            "site_location",

            "system_size",

            "panel_company",
            "panel_watt",
            "panel_quantity",

            "inverter_company",
            "inverter_model",

            "system_price",
            "structure_charge",
            "electrical_charge",
            "discount",
            "gst",
        ]