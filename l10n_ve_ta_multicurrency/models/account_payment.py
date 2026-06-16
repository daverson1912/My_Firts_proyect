from odoo import models, fields, api


# ---------------------------------------------------------------------------
# account.payment.register  (Wizard)
# ---------------------------------------------------------------------------
class AccountPaymentRegister(models.TransientModel):
    """
    EN: Extend the payment wizard with multicurrency rate and fiscal amount fields.
    ES: Extiende el asistente de pago con campos de tasa y monto fiscal multidivisa.
    """
    _inherit = 'account.payment.register'

    l10n_ve_ta_multicurrency_use_manual_rate = fields.Boolean(
        string='Use Manual Rate',
        default=False,
        help='EN: Mark to manually enter the exchange rate. | ES: Marque para ingresar manualmente la tasa de cambio.',
    )
    l10n_ve_ta_multicurrency_rate = fields.Float(
        string='Exchange Rate',
        digits=(12, 6),
        default=0.0,
        help='EN: Rate applied when registering the payment (defaults to day rate or manual). | ES: Tasa aplicada al momento de registrar el pago.',
    )
    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        compute='_compute_l10n_ve_ta_multicurrency_wizard_fiscal_id',
    )
    l10n_ve_ta_multicurrency_amount = fields.Monetary(
        string='Total Ref.',
        compute='_compute_l10n_ve_ta_multicurrency_wizard_amount',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
    )

    @api.depends('company_id')
    def _compute_l10n_ve_ta_multicurrency_wizard_fiscal_id(self):
        """
        EN: Find the fiscal currency for the wizard (per company).
        ES: Encuentra la moneda fiscal para el asistente (por compañía).
        """
        for wiz in self:
            fiscal = self.env['res.currency'].search([('l10n_ve_ta_multicurrency_is_fiscal', '=', True)], limit=1)
            if fiscal:
                wiz.l10n_ve_ta_multicurrency_fiscal_id = fiscal.id
                continue
            company_currency = wiz.company_id.currency_id
            if company_currency:
                foreign = self.env['res.currency'].search([
                    ('id', '!=', company_currency.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
                wiz.l10n_ve_ta_multicurrency_fiscal_id = foreign.id if foreign else False
            else:
                wiz.l10n_ve_ta_multicurrency_fiscal_id = False

    @api.depends(
        'amount', 'currency_id', 'payment_date',
        'l10n_ve_ta_multicurrency_use_manual_rate',
        'l10n_ve_ta_multicurrency_rate',
        'l10n_ve_ta_multicurrency_fiscal_id',
    )
    def _compute_l10n_ve_ta_multicurrency_wizard_amount(self):
        """
        EN: Compute the visualized amount in the fiscal currency for the wizard.
        ES: Calcula el monto visualizado en la moneda fiscal para el asistente.
        """
        for wiz in self:
            fiscal = wiz.l10n_ve_ta_multicurrency_fiscal_id
            if not fiscal or not wiz.currency_id:
                wiz.l10n_ve_ta_multicurrency_amount = 0.0
                continue

            if wiz.currency_id == fiscal:
                wiz.l10n_ve_ta_multicurrency_amount = wiz.amount
                continue

            if wiz.l10n_ve_ta_multicurrency_use_manual_rate and wiz.l10n_ve_ta_multicurrency_rate > 0:
                rate = wiz.l10n_ve_ta_multicurrency_rate
            else:
                date = wiz.payment_date or fields.Date.context_today(wiz)
                rate = wiz.env['res.currency']._get_conversion_rate(
                    wiz.currency_id, fiscal, wiz.company_id, date
                )
            wiz.l10n_ve_ta_multicurrency_amount = wiz.amount * rate

    def _get_payment_vals_list(self):
        """
        EN: Transfer the custom multicurrency fields from the wizard to the final payment record.
        ES: Transfiere los campos multidivisa personalizados del asistente al registro de pago final.
        """
        res = super()._get_payment_vals_list()
        for i, vals in enumerate(res):
            vals.update({
                'l10n_ve_ta_multicurrency_use_manual_rate': self.l10n_ve_ta_multicurrency_use_manual_rate,
                'l10n_ve_ta_multicurrency_rate': self.l10n_ve_ta_multicurrency_rate,
            })
        return res


# ---------------------------------------------------------------------------
# account.payment  (Final record)
# ---------------------------------------------------------------------------
class AccountPayment(models.Model):
    """
    EN: Extend account.payment with multicurrency rate and fiscal amount for audit trail.
    ES: Extiende account.payment con tasa multidivisa y monto fiscal para trazabilidad.
    """
    _inherit = 'account.payment'

    l10n_ve_ta_multicurrency_use_manual_rate = fields.Boolean(
        string='Use Manual Rate',
        default=False,
        help='EN: Mark to manually enter the exchange rate. | ES: Marque para ingresar manualmente la tasa de cambio.',
    )
    l10n_ve_ta_multicurrency_rate = fields.Float(
        string='Exchange Rate',
        digits=(12, 6),
        default=0.0,
        help='EN: Historical rate applied when the payment was processed. | ES: Tasa histórica con la que se procesó el pago.',
    )
    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_equivalent_id = fields.Many2one(
        'res.currency',
        compute='_compute_l10n_ve_ta_multicurrency_equivalent_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_amount = fields.Monetary(
        string='Total Ref.',
        compute='_compute_l10n_ve_ta_multicurrency_amount',
        currency_field='l10n_ve_ta_multicurrency_equivalent_id',
        store=True,
    )
    l10n_ve_ta_multicurrency_prev_currency_id = fields.Many2one(
        'res.currency',
        string='Prev Currency',
        compute='_compute_l10n_ve_ta_multicurrency_prev_currency_id',
        store=True,
        readonly=False,
    )

    @api.depends('journal_id')
    def _compute_l10n_ve_ta_multicurrency_prev_currency_id(self):
        """
        EN: Compute the previous currency to anchor price translation.
        ES: Calcula la moneda previa para anclar la traducción de precios.
        """
        for pay in self:
            if not pay.l10n_ve_ta_multicurrency_prev_currency_id:
                pay.l10n_ve_ta_multicurrency_prev_currency_id = pay.currency_id

    @api.onchange('currency_id')
    def _onchange_l10n_ve_ta_multicurrency_translate_amount(self):
        """
        EN: Mathematically translate the payment amount when switching currencies.
        ES: Traduce matemáticamente el monto del pago al cambiar de moneda.
        """
        if not self.l10n_ve_ta_multicurrency_prev_currency_id:
            self.l10n_ve_ta_multicurrency_prev_currency_id = self.currency_id
            return

        old_curr = self.l10n_ve_ta_multicurrency_prev_currency_id
        new_curr = self.currency_id

        if old_curr and new_curr and old_curr != new_curr and self.amount:
            rate = 1.0
            if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0:
                if old_curr == self.company_id.currency_id and new_curr == self.l10n_ve_ta_multicurrency_fiscal_id:
                    rate = self.l10n_ve_ta_multicurrency_rate
                elif old_curr == self.l10n_ve_ta_multicurrency_fiscal_id and new_curr == self.company_id.currency_id:
                    rate = 1.0 / self.l10n_ve_ta_multicurrency_rate if self.l10n_ve_ta_multicurrency_rate else 1.0
                else:
                    date_rate = self.date or fields.Date.context_today(self)
                    rate = self.env['res.currency']._get_conversion_rate(old_curr, new_curr, self.company_id, date_rate)
            else:
                date_rate = self.date or fields.Date.context_today(self)
                rate = self.env['res.currency']._get_conversion_rate(old_curr, new_curr, self.company_id, date_rate)

            self.amount = self.amount * rate

        self.l10n_ve_ta_multicurrency_prev_currency_id = self.currency_id

    @api.depends('company_id')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        EN: Find the fiscal currency per company.
        ES: Encuentra la moneda fiscal por compañía.
        """
        for pay in self:
            fiscal = self.env['res.currency'].search([('l10n_ve_ta_multicurrency_is_fiscal', '=', True)], limit=1)
            if fiscal:
                pay.l10n_ve_ta_multicurrency_fiscal_id = fiscal.id
                continue
            company_currency = pay.company_id.currency_id
            if company_currency:
                foreign = self.env['res.currency'].search([
                    ('id', '!=', company_currency.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
                pay.l10n_ve_ta_multicurrency_fiscal_id = foreign.id if foreign else False
            else:
                pay.l10n_ve_ta_multicurrency_fiscal_id = False

    @api.depends('currency_id', 'company_id', 'l10n_ve_ta_multicurrency_fiscal_id')
    def _compute_l10n_ve_ta_multicurrency_equivalent_id(self):
        """
        EN: Determine the opposite currency for multicurrency display.
        ES: Determina la moneda opuesta para la visualización multidivisa.
        """
        for pay in self:
            usd = pay.company_id.currency_id
            ves = pay.l10n_ve_ta_multicurrency_fiscal_id
            if pay.currency_id == usd:
                pay.l10n_ve_ta_multicurrency_equivalent_id = ves
            elif pay.currency_id == ves:
                pay.l10n_ve_ta_multicurrency_equivalent_id = usd
            else:
                pay.l10n_ve_ta_multicurrency_equivalent_id = ves

    @api.depends(
        'amount', 'currency_id', 'date',
        'l10n_ve_ta_multicurrency_use_manual_rate',
        'l10n_ve_ta_multicurrency_rate',
        'l10n_ve_ta_multicurrency_equivalent_id',
    )
    def _compute_l10n_ve_ta_multicurrency_amount(self):
        """
        EN: Compute the total payment amount in the equivalent fiscal currency.
        ES: Calcula el monto total del pago en la moneda fiscal equivalente.
        """
        for pay in self:
            if not pay.l10n_ve_ta_multicurrency_equivalent_id or not pay.currency_id:
                pay.l10n_ve_ta_multicurrency_amount = 0.0
                continue

            if pay.currency_id == pay.l10n_ve_ta_multicurrency_equivalent_id:
                pay.l10n_ve_ta_multicurrency_amount = pay.amount
                continue

            rate = 1.0
            if pay.l10n_ve_ta_multicurrency_use_manual_rate and pay.l10n_ve_ta_multicurrency_rate > 0:
                if pay.currency_id == pay.l10n_ve_ta_multicurrency_fiscal_id:
                    rate = 1.0 / pay.l10n_ve_ta_multicurrency_rate
                else:
                    rate = pay.l10n_ve_ta_multicurrency_rate
            else:
                date_rate = pay.date or fields.Date.context_today(pay)
                rate = self.env['res.currency']._get_conversion_rate(
                    pay.currency_id, pay.l10n_ve_ta_multicurrency_equivalent_id, pay.company_id, date_rate
                )

            pay.l10n_ve_ta_multicurrency_amount = pay.amount * rate

    def _get_common_move_vals_list(self):
        """
        EN: Transfer the multicurrency fields to the generated account.move header.
        ES: Transfiere los campos multidivisa a la cabecera del account.move generado.
        """
        res = super()._get_common_move_vals_list()
        for i, vals in enumerate(res):
            vals.update({
                'l10n_ve_ta_multicurrency_use_manual_rate': self.l10n_ve_ta_multicurrency_use_manual_rate,
                'l10n_ve_ta_multicurrency_rate': self.l10n_ve_ta_multicurrency_rate,
            })
        return res

    def _prepare_move_lines_per_type(self, write_off_line_vals=None, force_balance=None):
        """
        EN: Override to apply manual exchange rates to the generated journal entries.
        ES: Extensión para aplicar tasas de cambio manuales a los asientos contables generados.
        """
        res = super()._prepare_move_lines_per_type(write_off_line_vals=write_off_line_vals, force_balance=force_balance)

        if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0 and self.currency_id != self.company_id.currency_id:
            is_ves_to_usd = (self.currency_id == self.l10n_ve_ta_multicurrency_fiscal_id)

            for liquidity_line in res.get('liquidity_lines', []):
                amt = liquidity_line['amount_currency']
                manual_balance = amt / self.l10n_ve_ta_multicurrency_rate if is_ves_to_usd else amt * self.l10n_ve_ta_multicurrency_rate
                liquidity_line['balance'] = manual_balance

            for counterpart_line in res.get('counterpart_lines', []):
                amt = counterpart_line['amount_currency']
                manual_balance = amt / self.l10n_ve_ta_multicurrency_rate if is_ves_to_usd else amt * self.l10n_ve_ta_multicurrency_rate
                counterpart_line['balance'] = manual_balance

        return res
