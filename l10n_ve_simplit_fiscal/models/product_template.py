# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ve_apply_islr = fields.Boolean(
        string='Aplica ?',
        default=False,
        help='Indica si este producto o servicio está sujeto a retención de Impuesto Sobre la Renta.'
    )

    l10n_ve_islr_rate_id = fields.Many2one(
        'islr.retention.type',
        string='Concepto',
        help='Seleccione el concepto de retención aplicable para este producto/servicio.',
    )
