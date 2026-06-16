from odoo import fields, models


class TafelProviderOption(models.TransientModel):
    _name = 'tafel.provider.option'
    _description = 'Opción de Proveedor de Facturación'
    _rec_name = 'name'

    wizard_id = fields.Many2one('tafel.provider.setup.wizard', ondelete='cascade')
    provider_id_api = fields.Char()
    name = fields.Char()
    config_schema_json = fields.Text()
    payment_methods_json = fields.Text()
