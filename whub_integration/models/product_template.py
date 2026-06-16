from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class ProductTemplate(models.Model):
    """ Extensión de productos para almacenar IDs externos de WispHub """
    """ Product extension to store WispHub external IDs """
    _inherit = 'product.template'

    # Identificadores únicos de la API de WispHub / Unique WispHub API IDs
    whub_product_id = fields.Char(string='IDs WispHub', help="ID(s) único(s) del producto o plan en WispHub. Puede contener varios separados por coma.", copy=False)

    @api.constrains('whub_product_id')
    def _check_whub_product_id_unique(self):
        """ Valida que cada ID de WispHub en la lista de comas sea único en la base de datos de productos """
        for rec in self:
            if not rec.whub_product_id:
                continue
            # Obtener IDs individuales
            ids = [x.strip() for x in rec.whub_product_id.split(',') if x.strip()]
            for w_id in ids:
                domain = [
                    ('id', '!=', rec.id),
                    '|', ('whub_product_id', '=', w_id),
                    '|', ('whub_product_id', '=ilike', f'{w_id},%'),
                    '|', ('whub_product_id', '=ilike', f'%,{w_id}'),
                         ('whub_product_id', '=ilike', f'%,{w_id},%')
                ]
                duplicate = self.search(domain, limit=1)
                if duplicate:
                    raise ValidationError(_(
                        "El ID de producto/plan WispHub '%s' ya está asignado al producto '%s'."
                    ) % (w_id, duplicate.name))

    def _normalize_whub_product_id(self, whub_id):
        """ Normaliza el ID o IDs de producto WispHub eliminando espacios alrededor de las comas """
        if not whub_id:
            return False
        return ','.join([x.strip() for x in whub_id.split(',') if x.strip()])

    @api.model_create_multi
    def create(self, vals_list):
        """ Sobreescritura del método de creación para validaciones futuras """
        """ Creation method override for future validations """
        for vals in vals_list:
            if 'whub_product_id' in vals and vals['whub_product_id']:
                vals['whub_product_id'] = self._normalize_whub_product_id(vals['whub_product_id'])
        return super().create(vals_list)

    def write(self, vals):
        if 'whub_product_id' in vals and vals['whub_product_id']:
            vals['whub_product_id'] = self._normalize_whub_product_id(vals['whub_product_id'])
        return super().write(vals)

