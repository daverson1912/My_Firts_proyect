from odoo import api, fields, models


class TafelProviderPaymentMethod(models.Model):
    _name = 'tafel.provider.payment.method'
    _description = 'Método de Pago del Proveedor'
    _order = 'code'

    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='provider_config_id.company_id',
        store=True,
    )
    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Método de Pago', required=True)
    description = fields.Char(string='Descripción')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'[{rec.code}] {rec.name}' if rec.code else (rec.name or '')
