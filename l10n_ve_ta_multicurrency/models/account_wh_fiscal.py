# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

try:
    class AccountWhIva(models.Model):
        _inherit = 'account.wh.iva'

        l10n_ve_ta_multicurrency_amount_total_ret = fields.Monetary(
            string='Monto Retenido Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
            help="Monto total retenido de IVA convertido a la moneda de referencia."
        )
        l10n_ve_ta_multicurrency_base = fields.Monetary(
            string='Base Imponible Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
            help="Base imponible en la moneda de referencia asociada a la retención."
        )
        l10n_ve_ta_multicurrency_total_invoice = fields.Monetary(
            string='Monto Total Factura Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_taxable_base = fields.Monetary(
            string='Base Imponible Total Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_exempt = fields.Monetary(
            string='Monto Exento Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_amount_base = fields.Monetary(
            string='Impuesto Base (IVA) Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
            help="Impuesto base (IVA) en la moneda de referencia asociada a la retención."
        )
        l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
            'res.currency',
            string='Moneda de Referencia',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
            help="Moneda de referencia fiscal."
        )

        @api.depends('currency_id', 'company_id')
        def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
            for rec in self:
                doc_currency = rec.currency_id or rec.company_id.currency_id
                if doc_currency:
                    company_currency = rec.company_id.currency_id
                    if doc_currency == company_currency:
                        foreign = self.env['res.currency'].sudo().search([
                            ('id', '!=', company_currency.id),
                            ('active', '=', True)
                        ], order='name asc', limit=1)
                        rec.l10n_ve_ta_multicurrency_fiscal_id = foreign.id if foreign else False
                    else:
                        rec.l10n_ve_ta_multicurrency_fiscal_id = company_currency.id
                else:
                    rec.l10n_ve_ta_multicurrency_fiscal_id = False

        @api.depends('amount_total_ret', 'amount_taxable_base', 'amount_total_invoice', 'amount_exempt', 'amount_base', 'move_id.invoice_date', 'move_id.date', 'currency_id')
        def _compute_l10n_ve_ta_multicurrency_fiscal_amounts(self):
            for rec in self:
                source_currency = rec.currency_id or rec.company_id.currency_id
                ref_currency = rec.l10n_ve_ta_multicurrency_fiscal_id
                
                if source_currency and ref_currency and source_currency != ref_currency:
                    rate_date = rec.move_id.invoice_date or rec.move_id.date or fields.Date.context_today(rec) if rec.move_id else fields.Date.context_today(rec)
                    try:
                        factor = source_currency._get_conversion_rate(
                            source_currency, ref_currency, rec.company_id, rate_date
                        )
                    except Exception:
                        factor = 1.0
                else:
                    factor = 1.0
                
                rec.l10n_ve_ta_multicurrency_amount_total_ret = rec.amount_total_ret * factor
                rec.l10n_ve_ta_multicurrency_base = rec.amount_taxable_base * factor
                rec.l10n_ve_ta_multicurrency_total_invoice = rec.amount_total_invoice * factor
                rec.l10n_ve_ta_multicurrency_taxable_base = rec.amount_taxable_base * factor
                rec.l10n_ve_ta_multicurrency_exempt = rec.amount_exempt * factor
                rec.l10n_ve_ta_multicurrency_amount_base = rec.amount_base * factor
except TypeError:
    pass


try:
    class AccountWhIslr(models.Model):
        _inherit = 'account.wh.islr'

        l10n_ve_ta_multicurrency_amount_total_ret = fields.Monetary(
            string='Monto Retenido Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
            help="Monto total retenido de ISLR convertido a la moneda de referencia."
        )
        l10n_ve_ta_multicurrency_total_invoice = fields.Monetary(
            string='Monto Total Factura Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_taxable_base = fields.Monetary(
            string='Base Imponible Total Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_exempt = fields.Monetary(
            string='Monto Exento Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_amount_to_pay = fields.Monetary(
            string='Monto a Pagar Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
            'res.currency',
            string='Moneda de Referencia',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        )

        @api.depends('currency_id', 'company_id')
        def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
            for rec in self:
                doc_currency = rec.currency_id or rec.company_id.currency_id
                if doc_currency:
                    company_currency = rec.company_id.currency_id
                    if doc_currency == company_currency:
                        foreign = self.env['res.currency'].sudo().search([
                            ('id', '!=', company_currency.id),
                            ('active', '=', True)
                        ], order='name asc', limit=1)
                        rec.l10n_ve_ta_multicurrency_fiscal_id = foreign.id if foreign else False
                    else:
                        rec.l10n_ve_ta_multicurrency_fiscal_id = company_currency.id
                else:
                    rec.l10n_ve_ta_multicurrency_fiscal_id = False

        @api.depends('amount_total_ret', 'amount_taxable_base', 'amount_total_invoice', 'amount_exempt', 'amount_to_pay', 'move_id.invoice_date', 'move_id.date', 'currency_id')
        def _compute_l10n_ve_ta_multicurrency_fiscal_amounts(self):
            for rec in self:
                source_currency = rec.currency_id or rec.company_id.currency_id
                ref_currency = rec.l10n_ve_ta_multicurrency_fiscal_id
                
                if source_currency and ref_currency and source_currency != ref_currency:
                    rate_date = rec.move_id.invoice_date or rec.move_id.date or fields.Date.context_today(rec) if rec.move_id else fields.Date.context_today(rec)
                    try:
                        factor = source_currency._get_conversion_rate(
                            source_currency, ref_currency, rec.company_id, rate_date
                        )
                    except Exception:
                        factor = 1.0
                else:
                    factor = 1.0
                
                rec.l10n_ve_ta_multicurrency_amount_total_ret = rec.amount_total_ret * factor
                rec.l10n_ve_ta_multicurrency_total_invoice = rec.amount_total_invoice * factor
                rec.l10n_ve_ta_multicurrency_taxable_base = rec.amount_taxable_base * factor
                rec.l10n_ve_ta_multicurrency_exempt = rec.amount_exempt * factor
                rec.l10n_ve_ta_multicurrency_amount_to_pay = rec.amount_to_pay * factor
except TypeError:
    pass


try:
    class AccountWhIslrLine(models.Model):
        _inherit = 'account.wh.islr.line'

        l10n_ve_ta_multicurrency_base_amount = fields.Monetary(
            string='Monto Base Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_subject_amount = fields.Monetary(
            string='Monto Sujeto Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_base_retention_amount = fields.Monetary(
            string='Base Retención Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_retention_amount = fields.Monetary(
            string='Monto Retenido Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_subtrahend = fields.Monetary(
            string='Sustraendo Ref.',
            currency_field='l10n_ve_ta_multicurrency_fiscal_id',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_amounts',
            store=True,
        )
        l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
            'res.currency',
            string='Moneda de Referencia',
            related='islr_id.l10n_ve_ta_multicurrency_fiscal_id',
        )
        l10n_ve_ta_multicurrency_subject_amount_display = fields.Char(
            string='Base de la retención Ref.',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_displays',
        )
        l10n_ve_ta_multicurrency_retention_calculation_display = fields.Char(
            string='Calc. Imp Ref.',
            compute='_compute_l10n_ve_ta_multicurrency_fiscal_displays',
        )

        @api.depends('base_amount', 'subject_amount', 'base_retention_amount', 'retention_amount', 'subtrahend', 'islr_id.move_id.invoice_date', 'islr_id.move_id.date', 'currency_id')
        def _compute_l10n_ve_ta_multicurrency_fiscal_amounts(self):
            for rec in self:
                source_currency = rec.currency_id or rec.islr_id.company_id.currency_id
                ref_currency = rec.l10n_ve_ta_multicurrency_fiscal_id
                
                if source_currency and ref_currency and source_currency != ref_currency:
                    rate_date = rec.islr_id.move_id.invoice_date or rec.islr_id.move_id.date or fields.Date.context_today(rec) if rec.islr_id.move_id else fields.Date.context_today(rec)
                    try:
                        factor = source_currency._get_conversion_rate(
                            source_currency, ref_currency, rec.islr_id.company_id, rate_date
                        )
                    except Exception:
                        factor = 1.0
                else:
                    factor = 1.0
                
                rec.l10n_ve_ta_multicurrency_base_amount = rec.base_amount * factor
                rec.l10n_ve_ta_multicurrency_subject_amount = rec.subject_amount * factor
                rec.l10n_ve_ta_multicurrency_base_retention_amount = rec.base_retention_amount * factor
                rec.l10n_ve_ta_multicurrency_retention_amount = rec.retention_amount * factor
                rec.l10n_ve_ta_multicurrency_subtrahend = rec.subtrahend * factor

        @api.depends(
            'subject_amount',
            'subject_amount_percentage',
            'base_retention_amount',
            'retention_percentage',
            'islr_id.move_id.invoice_date',
            'islr_id.move_id.date',
            'currency_id',
        )
        def _compute_l10n_ve_ta_multicurrency_fiscal_displays(self):
            for rec in self:
                source_currency = rec.currency_id or rec.islr_id.company_id.currency_id
                ref_currency = rec.l10n_ve_ta_multicurrency_fiscal_id
                
                if source_currency and ref_currency and source_currency != ref_currency:
                    rate_date = rec.islr_id.move_id.invoice_date or rec.islr_id.move_id.date or fields.Date.context_today(rec) if rec.islr_id.move_id else fields.Date.context_today(rec)
                    try:
                        factor = source_currency._get_conversion_rate(
                            source_currency, ref_currency, rec.islr_id.company_id, rate_date
                        )
                    except Exception:
                        factor = 1.0
                else:
                    factor = 1.0
                
                subject_amount = rec.subject_amount * factor
                retention_calc_amount = rec.base_retention_amount * factor
                fiscal_curr = rec.l10n_ve_ta_multicurrency_fiscal_id
                symbol = fiscal_curr.symbol or fiscal_curr.name or ''
                
                subject_percentage = rec.subject_amount_percentage
                retention_percentage = rec.retention_percentage
                subject_percentage_txt = int(subject_percentage) if subject_percentage % 1 == 0 else subject_percentage
                retention_percentage_txt = int(retention_percentage) if retention_percentage % 1 == 0 else retention_percentage
 
                subject_formatted = "{:,.2f}".format(subject_amount).replace(",", "X").replace(".", ",").replace("X", ".")
                retention_formatted = "{:,.2f}".format(retention_calc_amount).replace(",", "X").replace(".", ",").replace("X", ".")
 
                if symbol:
                    rec.l10n_ve_ta_multicurrency_subject_amount_display = f"{subject_formatted} {symbol} ({subject_percentage_txt}%)"
                    rec.l10n_ve_ta_multicurrency_retention_calculation_display = f"{retention_formatted} {symbol} ({retention_percentage_txt}%)"
                else:
                    rec.l10n_ve_ta_multicurrency_subject_amount_display = f"{subject_formatted} ({subject_percentage_txt}%)"
                    rec.l10n_ve_ta_multicurrency_retention_calculation_display = f"{retention_formatted} ({retention_percentage_txt}%)"
except TypeError:
    pass
