from odoo import fields, models


class TafelPaymentMethodMap(models.Model):
    _name = 'tafel.payment.method.map'
    _description = 'Mapeo de Métodos de Pago'

    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='provider_config_id.company_id',
        store=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Pago',
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    provider_payment_method_id = fields.Many2one(
        'tafel.provider.payment.method',
        string='Método del Proveedor',
        required=True,
        domain="[('provider_config_id', '=', provider_config_id)]",
        ondelete='restrict',
    )
    provider_code = fields.Char(
        related='provider_payment_method_id.code',
        string='Código',
        store=True,
    )
