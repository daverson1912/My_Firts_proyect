from odoo import models, fields, api

class AccountBatchPayment(models.Model):
    _inherit = 'account.batch.payment'

    l10n_ve_ta_multicurrency_batch_fiscal_id = fields.Many2one(
        'res.currency',
        string='Fiscal Currency equivalent for batch',
        compute='_compute_l10n_ve_ta_multicurrency_batch_fiscal_id',
        store=True,
    )

    l10n_ve_ta_multicurrency_amount = fields.Monetary(
        string='Total Ref.',
        currency_field='l10n_ve_ta_multicurrency_batch_fiscal_id',
        compute='_compute_l10n_ve_ta_multicurrency_amount_batch',
        store=True,
    )

    @api.depends('payment_ids.l10n_ve_ta_multicurrency_equivalent_id')
    def _compute_l10n_ve_ta_multicurrency_batch_fiscal_id(self):
        for batch in self:
            fiscal_id = False
            if batch.payment_ids:
                # Assuming all payments in batch share the same fiscal/equivalent currency
                for p in batch.payment_ids:
                    if p.l10n_ve_ta_multicurrency_equivalent_id:
                        fiscal_id = p.l10n_ve_ta_multicurrency_equivalent_id.id
                        break
            
            # Fallback if no payments: try to find the marked fiscal currency (per company)
            if not fiscal_id:
                fiscal = self.env['res.currency'].search([('l10n_ve_ta_multicurrency_is_fiscal', '=', True)], limit=1)
                if fiscal:
                    fiscal_id = fiscal.id
                else:
                    company_currency = batch.company_id.currency_id or self.env.company.currency_id
                    foreign = self.env['res.currency'].search([
                        ('id', '!=', company_currency.id),
                        ('active', '=', True)
                    ], order='name asc', limit=1)
                    fiscal_id = foreign.id if foreign else company_currency.id
                
            batch.l10n_ve_ta_multicurrency_batch_fiscal_id = fiscal_id

    @api.depends('payment_ids.l10n_ve_ta_multicurrency_amount', 'l10n_ve_ta_multicurrency_batch_fiscal_id')
    def _compute_l10n_ve_ta_multicurrency_amount_batch(self):
        for batch in self:
            total = 0.0
            for payment in batch.payment_ids:
                total += payment.l10n_ve_ta_multicurrency_amount
            batch.l10n_ve_ta_multicurrency_amount = total

