from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    is_simplit_tax = fields.Boolean(
        string='Es Impuesto Simplit',
        default=False,
        help='Indica si este impuesto fue generado por el módulo Simplit Fiscal'
    )

    simplit_tax_type = fields.Selection([
        # --- VALORES ANTIGUOS (Compatibilidad) ---
        ('iva_16', 'IVA 16%'),
        ('iva_8', 'IVA 8%'),
        ('ret_75', 'Retención 75%'),
        ('ret_100', 'Retención 100%'),
        ('ret_ivar_75', 'Retención IVAR 75%'),
        ('ret_ivar_100', 'Retención IVAR 100%'),
        ('group_iva_ret_75', 'Grupo IVA 16% + Ret 75%'),
        ('group_iva_ret_100', 'Grupo IVA 16% + Ret 100%'),
        ('group_ivar_ret_75', 'Grupo IVA 8% + Ret 75%'),
        ('group_ivar_ret_100', 'Grupo IVA 8% + Ret 100%'),
        # --- NUEVOS VALORES (Compras) ---
        ('purchase_iva_16', 'IVA 16% (Compras)'),
        ('purchase_iva_8', 'IVA 8% (Compras)'),
        ('purchase_ret_75', 'Retención 75% (Compras)'),
        ('purchase_ret_100', 'Retención 100% (Compras)'),
        ('purchase_ret_ivar_75', 'Retención IVAR 75% (Compras)'),
        ('purchase_ret_ivar_100', 'Retención IVAR 100% (Compras)'),
        ('purchase_group_iva_ret_75', 'Grupo IVA 16% + Ret 75% (Compras)'),
        ('purchase_group_iva_ret_100', 'Grupo IVA 16% + Ret 100% (Compras)'),
        ('purchase_group_ivar_ret_75', 'Grupo IVA 8% + Ret 75% (Compras)'),
        ('purchase_group_ivar_ret_100', 'Grupo IVA 8% + Ret 100% (Compras)'),
        # --- NUEVOS VALORES (Ventas) ---
        ('sale_iva_16', 'IVA 16% (Ventas)'),
        ('sale_iva_8', 'IVA 8% (Ventas)'),
        ('sale_ret_75', 'Retención 75% (Ventas)'),
        ('sale_ret_100', 'Retención 100% (Ventas)'),
        ('sale_ret_ivar_75', 'Retención IVAR 75% (Ventas)'),
        ('sale_ret_ivar_100', 'Retención IVAR 100% (Ventas)'),
        ('sale_group_iva_ret_75', 'Grupo IVA 16% + Ret 75% (Ventas)'),
        ('sale_group_iva_ret_100', 'Grupo IVA 16% + Ret 100% (Ventas)'),
        ('sale_group_ivar_ret_75', 'Grupo IVA 8% + Ret 75% (Ventas)'),
        ('sale_group_ivar_ret_100', 'Grupo IVA 8% + Ret 100% (Ventas)'),
    ], string='Tipo de Impuesto Simplit', help="Identificador técnico para búsquedas fiscales", index=True)

    is_retention = fields.Boolean(
        string='Es Retención',
        default=False,
        help='Indica si este impuesto es una retención (para mostrarse en la parte inferior del pie de página).',
    )
