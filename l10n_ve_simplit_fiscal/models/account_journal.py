# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_ve_affects_sales_ledger = fields.Boolean(
        string='¿Afecta Libro de Venta?',
        default=False,
        help='Indica si este diario debe incluirse en el Libro Fiscal de Ventas.',
    )

    l10n_ve_affects_purchase_ledger = fields.Boolean(
        string='¿Afecta Libro de Compra?',
        default=False,
        help='Indica si este diario debe incluirse en el Libro Fiscal de Compras.',
    )
