from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    tafel_full_address = fields.Char(
        string='Dirección Completa (Tafel)',
        compute='_compute_tafel_full_address',
        store=False,
    )

    @api.depends('street', 'street2')
    def _compute_tafel_full_address(self):
        for rec in self:
            parts = [rec.street, rec.street2]
            rec.tafel_full_address = ', '.join(p for p in parts if p)
