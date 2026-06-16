# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):
    """
    Extensión del modelo de Compañía para agregar configuración de
    Agente de Retención IVA (Contribuyente Especial) en Venezuela.
    """
    _inherit = 'res.company'

    l10n_ve_is_withholding_agent = fields.Boolean(
        string='Es Agente de Retención IVA',
        help='Indica si esta empresa es un Contribuyente Especial designado '
             'por el SENIAT como Agente de Retención de IVA en Venezuela. '
             'Cuando está activo, las facturas de proveedor aplicarán '
             'automáticamente retenciones según la configuración del proveedor.',
        default=False,
    )

    l10n_ve_agent_signature = fields.Binary(
        string='Firma y Sello del Agente',
        help='Imagen de la firma y sello del agente de retención para los comprobantes.',
    )

    @api.depends('country_id')
    def _compute_l10n_ve_fields_visible(self):
        """
        Calcula si los campos específicos de Venezuela deben ser visibles.
        Solo se muestran si el país de la compañía es Venezuela.
        """
        for company in self:
            company.l10n_ve_fields_visible = company.country_id.code == 'VE'

    l10n_ve_fields_visible = fields.Boolean(
        string='Campos Venezuela Visibles',
        compute='_compute_l10n_ve_fields_visible',
        store=False,
        help='Campo técnico para controlar la visibilidad de campos específicos de Venezuela.'
    )
