from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    l10n_ve_supplier_retention_type = fields.Selection(
        selection=[
            ('75', '75%'),
            ('100', '100%'),
        ],
        string='Porcentaje',
        help='Porcentaje de retención de IVA que se aplicará automáticamente '
             'en las facturas de compra a este proveedor.',
    )
    
    @api.depends('supplier_rank', 'customer_rank')
    def _compute_l10n_ve_show_retention(self):
        """Determina si se debe mostrar el campo de retención."""
        for partner in self:
            # Mostrar si es proveedor o cliente, o si estamos en contexto de crear uno
            is_fiscal_subject = (
                partner.supplier_rank > 0 or 
                partner.customer_rank > 0 or
                self._context.get('default_supplier_rank', 0) > 0 or 
                self._context.get('default_customer_rank', 0) > 0 or
                self._context.get('res_partner_search_mode') in ('supplier', 'customer')
            )
            company = self.env.company
            is_venezuela = company.country_id.code == 'VE' if company.country_id else False
            partner.l10n_ve_show_retention = is_fiscal_subject and is_venezuela
    
    l10n_ve_show_retention = fields.Boolean(
        compute='_compute_l10n_ve_show_retention',
        string='Mostrar Retención VE',
        store=False,
    )

    l10n_ve_is_wh_iva_agent = fields.Boolean(
        string='Es Agente de Retención IVA',
        help='Indica si este proveedor es sujeto a retención de IVA.',
    )

    l10n_ve_customer_iva_agent = fields.Boolean(
        string='Agente de Retención IVA (Cliente)',
        help='Indica si este cliente es agente de retención de IVA y nos retendrá en ventas.',
    )

    # ========== RETENCIÓN ISLR ==========

    l10n_ve_islr_provider_type_id = fields.Many2one(
        'islr.provider.type',
        string='Beneficiario de Pago',
        help='Tipo de proveedor para el cálculo de retención de ISLR.',
    )

    l10n_ve_is_islr_payer = fields.Boolean(
        string='Sujeto a Retención',
        default=False,
        help='Indica si este contacto está sujeto a retención de ISLR.',
    )
