# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class AccountLoan(models.Model):
    _inherit = 'account.loan'

    l10n_ve_ta_multicurrency_amount_borrowed_ref = fields.Monetary(
        string="Loan Ref.",
        compute='_compute_l10n_ve_ta_multicurrency_loan_ref',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_outstanding_balance_ref = fields.Monetary(
        string="Balance Ref.",
        compute='_compute_l10n_ve_ta_multicurrency_loan_ref',
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
    )
    l10n_ve_ta_multicurrency_applied_rate = fields.Float(
        string="Applied Rate",
        compute='_compute_l10n_ve_ta_multicurrency_applied_rate',
        digits=(12, 6),
        store=True,
        readonly=False,
    )

    @api.depends('currency_id')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        Lógica Bimonetaria Estricta Genérica:
        Determina de forma genérica la divisa de referencia del préstamo.
        """
        for loan in self:
            company_currency = loan.company_id.currency_id
            if not company_currency:
                loan.l10n_ve_ta_multicurrency_fiscal_id = False
                continue
            
            loan_is_company_curr = (loan.currency_id == company_currency)
            
            if loan_is_company_curr:
                # Si el préstamo está en la moneda de la compañía, la de referencia es la extranjera
                foreign_curr = self.env['res.currency'].sudo().search([
                    ('id', '!=', company_currency.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
                loan.l10n_ve_ta_multicurrency_fiscal_id = foreign_curr.id if foreign_curr else False
            else:
                loan.l10n_ve_ta_multicurrency_fiscal_id = company_currency.id

    @api.depends('date', 'l10n_ve_ta_multicurrency_fiscal_id', 'l10n_ve_ta_multicurrency_use_manual_rate', 'currency_id')
    def _compute_l10n_ve_ta_multicurrency_applied_rate(self):
        """
        Calcula la tasa aplicada de forma 100% genérica.
        """
        for loan in self:
            if loan.l10n_ve_ta_multicurrency_use_manual_rate:
                if not loan.l10n_ve_ta_multicurrency_applied_rate:
                    loan.l10n_ve_ta_multicurrency_applied_rate = 1.0
                continue

            doc_currency = loan.currency_id
            target_currency = loan.l10n_ve_ta_multicurrency_fiscal_id
            company_currency = loan.company_id.currency_id

            if not doc_currency or not target_currency or not company_currency:
                loan.l10n_ve_ta_multicurrency_applied_rate = 1.0
                continue
            
            if doc_currency == target_currency:
                loan.l10n_ve_ta_multicurrency_applied_rate = 1.0
                continue

            # Identificamos la divisa extranjera
            foreign_currency = doc_currency if doc_currency != company_currency else target_currency
            
            rate_date = loan.date or fields.Date.today()
            rate_obj = self.env['res.currency.rate'].search([
                ('currency_id', '=', foreign_currency.id),
                ('company_id', '=', loan.company_id.id),
                ('name', '<=', rate_date),
            ], order='name desc', limit=1)
            
            if rate_obj and rate_obj.rate > 0:
                if rate_obj.rate < 1.0:
                    loan.l10n_ve_ta_multicurrency_applied_rate = 1.0 / rate_obj.rate
                else:
                    loan.l10n_ve_ta_multicurrency_applied_rate = rate_obj.rate
            else:
                # Fallback nativo
                rate = doc_currency._get_conversion_rate(doc_currency, target_currency, loan.company_id, rate_date)
                loan.l10n_ve_ta_multicurrency_applied_rate = rate or 1.0

    @api.depends('amount_borrowed', 'outstanding_balance', 'l10n_ve_ta_multicurrency_applied_rate', 'currency_id')
    def _compute_l10n_ve_ta_multicurrency_loan_ref(self):
        """
        Calcula los valores espejo del préstamo basándose en la tasa aplicada y de forma genérica.
        """
        for loan in self:
            if not loan.currency_id:
                loan.l10n_ve_ta_multicurrency_amount_borrowed_ref = 0.0
                loan.l10n_ve_ta_multicurrency_outstanding_balance_ref = 0.0
                continue
            
            rate = loan.l10n_ve_ta_multicurrency_applied_rate or 1.0
            
            # Si el préstamo está en la moneda de la compañía -> DIVIDIR
            if loan.currency_id == loan.company_id.currency_id:
                loan.l10n_ve_ta_multicurrency_amount_borrowed_ref = loan.amount_borrowed / rate if rate > 0 else loan.amount_borrowed
                loan.l10n_ve_ta_multicurrency_outstanding_balance_ref = loan.outstanding_balance / rate if rate > 0 else loan.outstanding_balance
            else:
                # Si el préstamo está en moneda extranjera -> MULTIPLICAR
                loan.l10n_ve_ta_multicurrency_amount_borrowed_ref = loan.amount_borrowed * rate
                loan.l10n_ve_ta_multicurrency_outstanding_balance_ref = loan.outstanding_balance * rate

class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        related='loan_id.l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_payment_ref = fields.Monetary(
        string="Payment Ref.",
        compute='_compute_l10n_ve_ta_multicurrency_payment_ref',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )

    @api.depends('payment', 'loan_id.l10n_ve_ta_multicurrency_applied_rate', 'currency_id')
    def _compute_l10n_ve_ta_multicurrency_payment_ref(self):
        """
        Calcula las cuotas del préstamo en moneda espejo.
        """
        for line in self:
            if not line.currency_id:
                line.l10n_ve_ta_multicurrency_payment_ref = 0.0
                continue
            
            rate = line.loan_id.l10n_ve_ta_multicurrency_applied_rate or 1.0
            
            # Si la línea está en la moneda de la compañía -> DIVIDIR
            if line.currency_id == line.company_id.currency_id:
                line.l10n_ve_ta_multicurrency_payment_ref = line.payment / rate if rate > 0 else line.payment
            else:
                # Si está en moneda extranjera -> MULTIPLICAR
                line.l10n_ve_ta_multicurrency_payment_ref = line.payment * rate
