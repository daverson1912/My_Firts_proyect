# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    l10n_ve_ta_multicurrency_original_value_ref = fields.Monetary(
        string="Total Ref.",
        compute='_compute_l10n_ve_ta_multicurrency_asset_ref',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
        help="EN: Original value in reference (fiscal) currency. ES: Valor original en moneda de referencia (fiscal)."
    )
    l10n_ve_ta_multicurrency_book_value_ref = fields.Monetary(
        string="Book Value Ref.",
        compute='_compute_l10n_ve_ta_multicurrency_asset_ref',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_value_residual_ref = fields.Monetary(
        string="Depreciable Value Ref.",
        compute='_compute_l10n_ve_ta_multicurrency_asset_ref',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        string="Fiscal Currency",
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        store=True
    )
    l10n_ve_ta_multicurrency_use_manual_rate = fields.Boolean(
        string="Use Manual Rate",
        default=False,
        help="EN: Mark to manually enter the exchange rate. | ES: Marque para ingresar manualmente la tasa de cambio."
    )
    l10n_ve_ta_multicurrency_applied_rate = fields.Float(
        string="Applied Rate",
        compute='_compute_l10n_ve_ta_multicurrency_applied_rate',
        digits=(12, 6),
        store=True,
        readonly=False,
        help="EN: Exchange rate used for this asset. ES: Tasa de cambio utilizada para este activo."
    )

    @api.depends('currency_id')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        Determina de forma genérica la divisa de referencia del activo.
        """
        for asset in self:
            company_currency = asset.company_id.currency_id
            if not company_currency:
                asset.l10n_ve_ta_multicurrency_fiscal_id = False
                continue
            
            asset_is_company_curr = (asset.currency_id == company_currency)
            
            if asset_is_company_curr:
                # Si el activo está en la moneda de la compañía, la de referencia es la extranjera
                foreign_curr = self.env['res.currency'].sudo().search([
                    ('id', '!=', company_currency.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
                asset.l10n_ve_ta_multicurrency_fiscal_id = foreign_curr.id if foreign_curr else False
            else:
                asset.l10n_ve_ta_multicurrency_fiscal_id = company_currency.id

    @api.depends('acquisition_date', 'l10n_ve_ta_multicurrency_fiscal_id', 'l10n_ve_ta_multicurrency_use_manual_rate')
    def _compute_l10n_ve_ta_multicurrency_applied_rate(self):
        """
        Calcula la tasa aplicada de forma 100% genérica.
        """
        for asset in self:
            if asset.l10n_ve_ta_multicurrency_use_manual_rate:
                if not asset.l10n_ve_ta_multicurrency_applied_rate:
                    asset.l10n_ve_ta_multicurrency_applied_rate = 1.0
                continue

            doc_currency = asset.currency_id
            target_currency = asset.l10n_ve_ta_multicurrency_fiscal_id
            company_currency = asset.company_id.currency_id

            if not doc_currency or not target_currency or not company_currency or not asset.acquisition_date:
                asset.l10n_ve_ta_multicurrency_applied_rate = 1.0
                continue
            
            if doc_currency == target_currency:
                asset.l10n_ve_ta_multicurrency_applied_rate = 1.0
                continue

            # Identificamos la divisa extranjera
            foreign_currency = doc_currency if doc_currency != company_currency else target_currency
            
            rate_date = asset.acquisition_date
            rate_obj = self.env['res.currency.rate'].search([
                ('currency_id', '=', foreign_currency.id),
                ('company_id', '=', asset.company_id.id),
                ('name', '<=', rate_date),
            ], order='name desc', limit=1)
            
            if rate_obj and rate_obj.rate > 0:
                if rate_obj.rate < 1.0:
                    asset.l10n_ve_ta_multicurrency_applied_rate = 1.0 / rate_obj.rate
                else:
                    asset.l10n_ve_ta_multicurrency_applied_rate = rate_obj.rate
            else:
                # Fallback nativo
                rate = doc_currency._get_conversion_rate(doc_currency, target_currency, asset.company_id, rate_date)
                asset.l10n_ve_ta_multicurrency_applied_rate = rate or 1.0

    @api.depends('original_value', 'book_value', 'value_residual', 'l10n_ve_ta_multicurrency_applied_rate', 'currency_id')
    def _compute_l10n_ve_ta_multicurrency_asset_ref(self):
        """
        Calcula los valores espejo del activo basándose en la tasa aplicada y de forma genérica.
        """
        for asset in self:
            if not asset.currency_id:
                asset.l10n_ve_ta_multicurrency_original_value_ref = 0.0
                asset.l10n_ve_ta_multicurrency_book_value_ref = 0.0
                asset.l10n_ve_ta_multicurrency_value_residual_ref = 0.0
                continue
            
            rate = asset.l10n_ve_ta_multicurrency_applied_rate or 1.0
            
            # Si el documento está en la moneda de la compañía -> DIVIDIR
            if asset.currency_id == asset.company_id.currency_id:
                asset.l10n_ve_ta_multicurrency_original_value_ref = asset.original_value / rate if rate > 0 else asset.original_value
                asset.l10n_ve_ta_multicurrency_book_value_ref = asset.book_value / rate if rate > 0 else asset.book_value
                asset.l10n_ve_ta_multicurrency_value_residual_ref = asset.value_residual / rate if rate > 0 else asset.value_residual
            else:
                # Si el documento está en moneda extranjera -> MULTIPLICAR
                asset.l10n_ve_ta_multicurrency_original_value_ref = asset.original_value * rate
                asset.l10n_ve_ta_multicurrency_book_value_ref = asset.book_value * rate
                asset.l10n_ve_ta_multicurrency_value_residual_ref = asset.value_residual * rate
