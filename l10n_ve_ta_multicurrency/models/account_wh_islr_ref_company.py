# -*- coding: utf-8 -*-

from odoo import api, fields, models


try:
    class AccountWhIslrLine(models.Model):
        _inherit = 'account.wh.islr.line'

        l10n_ve_ta_multicurrency_company_currency_id = fields.Many2one(
            'res.currency',
            string='Moneda Base Compañía',
            related='islr_id.company_id.currency_id',
            readonly=True,
        )
        l10n_ve_ta_multicurrency_base_amount_company = fields.Float(
            string='Base Imponible Ref. Base',
            digits=(16, 4),
            compute='_compute_l10n_ve_ta_multicurrency_company_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_subtrahend_company = fields.Float(
            string='Sustraendo Ref. Base',
            digits=(16, 4),
            compute='_compute_l10n_ve_ta_multicurrency_company_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_retention_amount_company = fields.Float(
            string='Monto Retenido Ref. Base',
            digits=(16, 4),
            compute='_compute_l10n_ve_ta_multicurrency_company_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_subject_amount_display_company = fields.Char(
            string='Base de la retención Ref.',
            compute='_compute_l10n_ve_ta_multicurrency_company_displays',
        )
        l10n_ve_ta_multicurrency_retention_calculation_display_company = fields.Char(
            string='Calc. Imp Ref.',
            compute='_compute_l10n_ve_ta_multicurrency_company_displays',
        )

        @api.depends(
            'base_amount',
            'subtrahend',
            'retention_amount',
            'currency_id',
            'islr_id.company_id',
            'islr_id.date',
            'islr_id.invoice_date',
        )
        def _compute_l10n_ve_ta_multicurrency_company_amounts(self):
            for rec in self:
                target_currency = rec.l10n_ve_ta_multicurrency_company_currency_id
                source_currency = rec.currency_id or target_currency
                company = rec.islr_id.company_id
                date = rec.islr_id.invoice_date or rec.islr_id.date or fields.Date.context_today(rec)

                if not source_currency or not target_currency or not company:
                    rec.l10n_ve_ta_multicurrency_base_amount_company = rec.base_amount
                    rec.l10n_ve_ta_multicurrency_subtrahend_company = rec.subtrahend
                    rec.l10n_ve_ta_multicurrency_retention_amount_company = rec.retention_amount
                    continue

                if source_currency == target_currency:
                    rec.l10n_ve_ta_multicurrency_base_amount_company = rec.base_amount
                    rec.l10n_ve_ta_multicurrency_subtrahend_company = rec.subtrahend
                    rec.l10n_ve_ta_multicurrency_retention_amount_company = rec.retention_amount
                    continue

                rec.l10n_ve_ta_multicurrency_base_amount_company = source_currency._convert(
                    rec.base_amount,
                    target_currency,
                    company,
                    date,
                )
                rec.l10n_ve_ta_multicurrency_subtrahend_company = source_currency._convert(
                    rec.subtrahend,
                    target_currency,
                    company,
                    date,
                )
                rec.l10n_ve_ta_multicurrency_retention_amount_company = source_currency._convert(
                    rec.retention_amount,
                    target_currency,
                    company,
                    date,
                )

        @api.depends(
            'subject_amount',
            'subject_amount_percentage',
            'base_retention_amount',
            'retention_percentage',
            'currency_id',
            'islr_id.company_id',
            'islr_id.date',
            'islr_id.invoice_date',
        )
        def _compute_l10n_ve_ta_multicurrency_company_displays(self):
            for rec in self:
                target_currency = rec.l10n_ve_ta_multicurrency_company_currency_id
                source_currency = rec.currency_id or target_currency
                company = rec.islr_id.company_id
                date = rec.islr_id.invoice_date or rec.islr_id.date or fields.Date.context_today(rec)

                subject_amount = rec.subject_amount
                retention_calc_amount = rec.base_retention_amount
                if source_currency and target_currency and company and source_currency != target_currency:
                    subject_amount = source_currency._convert(subject_amount, target_currency, company, date)
                    retention_calc_amount = source_currency._convert(retention_calc_amount, target_currency, company, date)

                symbol = target_currency.symbol if target_currency else ''
                subject_percentage = rec.subject_amount_percentage
                retention_percentage = rec.retention_percentage
                subject_percentage_txt = int(subject_percentage) if subject_percentage % 1 == 0 else subject_percentage
                retention_percentage_txt = int(retention_percentage) if retention_percentage % 1 == 0 else retention_percentage

                subject_formatted = "{:,.2f}".format(subject_amount).replace(",", "X").replace(".", ",").replace("X", ".")
                retention_formatted = "{:,.2f}".format(retention_calc_amount).replace(",", "X").replace(".", ",").replace("X", ".")

                if symbol:
                    rec.l10n_ve_ta_multicurrency_subject_amount_display_company = f"{subject_formatted} {symbol} ({subject_percentage_txt}%)"
                    rec.l10n_ve_ta_multicurrency_retention_calculation_display_company = f"{retention_formatted} {symbol} ({retention_percentage_txt}%)"
                else:
                    rec.l10n_ve_ta_multicurrency_subject_amount_display_company = f"{subject_formatted} ({subject_percentage_txt}%)"
                    rec.l10n_ve_ta_multicurrency_retention_calculation_display_company = f"{retention_formatted} ({retention_percentage_txt}%)"
except TypeError:
    pass
