from odoo import api, fields, models


class TafelCustomField(models.Model):
    _name = 'tafel.custom.field'
    _description = 'Campo Adicional Personalizado — Factura Electrónica'
    _order = 'sequence, id'
    _rec_name = 'name'

    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='provider_config_id.company_id',
        store=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(
        string='Nombre del Campo',
        required=True,
        help='Clave que aparecerá en el JSON (campo "field" del additionalInfo).',
    )
    source_model = fields.Selection([
        ('move', 'Factura'),
        ('line', 'Línea de Factura'),
    ], string='Contexto', required=True, default='move',
        help='Nivel del payload donde se incluye este campo: '
             'Factura = additionalInfo en la cabecera, '
             'Línea de Factura = additionalInfo en cada ítem.')
    value_type = fields.Selection([
        ('manual', 'Manual'),
        ('auto', 'Automatizado'),
        ('template', 'Plantilla'),
    ], string='Tipo de Valor', required=True, default='manual',
        help='Manual: escribe el valor directamente. '
             'Automatizado: se obtiene de un campo de Odoo. '
             'Plantilla: texto libre con <<campo>> o <<campo:formato>>.')
    odoo_expr = fields.Char(
        string='Expresión Odoo',
        help='Ruta dot-notation evaluada contra account.move (cabecera) o '
             'account.move.line (ítem). Ej: partner_id.ref, product_id.default_code.',
    )
    default_value = fields.Char(
        string='Valor Fijo',
        help='Valor estático o fallback cuando la expresión Odoo está vacía o no retorna nada.',
    )
    template_text = fields.Text(
        string='Plantilla',
        help='Texto con placeholders <<campo>> o <<campo:formato>>. '
             'También acepta un JSON donde cada valor es una plantilla, '
             'generando múltiples entradas de additionalInfo.',
    )

    # --- Helpers visuales para seleccionar campo Odoo ---
    source_model_technical = fields.Char(
        compute='_compute_source_model_technical',
        store=False,
    )
    odoo_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo',
        ondelete='set null',
        domain="[('model_id.model', '=', source_model_technical), "
               " ('ttype', 'not in', ['one2many', 'many2many', 'binary'])]",
        help='Selector del campo Odoo del modelo indicado en Contexto.',
    )
    odoo_field_relation = fields.Char(
        related='odoo_field_id.relation',
        store=False,
    )
    odoo_related_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo Secundario',
        ondelete='set null',
        domain="[('model_id.model', '=', odoo_field_relation), "
               " ('ttype', 'not in', ['one2many', 'many2many', 'binary'])]",
        help='Campo del modelo relacionado para expresiones de dos niveles.',
    )

    @api.depends('source_model')
    def _compute_source_model_technical(self):
        mapping = {'move': 'account.move', 'line': 'account.move.line'}
        for rec in self:
            rec.source_model_technical = mapping.get(rec.source_model, 'account.move')

    @api.onchange('odoo_field_id')
    def _onchange_odoo_field_id(self):
        self.odoo_related_field_id = False
        if self.odoo_field_id:
            self.odoo_expr = self.odoo_field_id.name

    @api.onchange('odoo_related_field_id')
    def _onchange_odoo_related_field_id(self):
        if self.odoo_related_field_id and self.odoo_field_id:
            self.odoo_expr = f'{self.odoo_field_id.name}.{self.odoo_related_field_id.name}'
