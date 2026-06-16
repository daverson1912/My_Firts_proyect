from odoo import models, fields, api

class IslrProviderType(models.Model):
    _name = 'islr.provider.type'
    _description = 'Tipo de Proveedor ISLR'
    _rec_name = 'display_name'

    code = fields.Char(string='Código', required=True)
    guid = fields.Char(string='GUID', required=True)
    description = fields.Char(string='Descripción', required=True)

    @api.depends('code', 'description')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} - {rec.description}"

class IslrRetentionType(models.Model):
    _name = 'islr.retention.type'
    _description = 'Concepto de Retención ISLR'
    _rec_name = 'description'

    # Valid fields from /api/v1/master-data/retention-types
    guid = fields.Char(string='GUID', required=True)
    description = fields.Char(string='Descripción', required=True)
