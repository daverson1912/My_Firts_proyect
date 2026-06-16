from odoo import models, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model
    def _get_tax_totals_summary(self, base_lines, currency, company, cash_rounding=None):
        """
        EN: Clean up the tax totals summary to remove Odoo's native multicurrency conversions.
        ES: Limpia el resumen de totales de impuestos para eliminar las conversiones multimoneda nativas de Odoo.
        """
        res = super()._get_tax_totals_summary(base_lines, currency, company, cash_rounding=cash_rounding)
        if res and isinstance(res, dict):
            # Globally disable the flag that tells OWL to show company currency on tax groups
            res['display_in_company_currency'] = False
            
            # Remove the parenthesized Total Ref from the dictionary if any core module added it
            if 'amount_total_cc' in res:
                res['amount_total_cc'] = ''

        return res
