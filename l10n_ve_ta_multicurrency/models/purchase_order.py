from odoo import models, fields, api


class PurchaseOrder(models.Model):
    """
    EN: Extend purchase.order with multicurrency fields for manual rate and fiscal totals.
    ES: Extiende purchase.order con campos multidivisa para tasa manual y totales fiscales.
    """
    _inherit = 'purchase.order'

    l10n_ve_ta_multicurrency_use_manual_rate = fields.Boolean(
        string='Use Manual Rate',
        default=False,
        help="EN: Mark to manually enter the exchange rate. | ES: Marque para ingresar manualmente la tasa de cambio.",
    )
    l10n_ve_ta_multicurrency_rate = fields.Float(
        string='Exchange Rate',
        digits=(12, 6),
        default=0.0,
        help="EN: Manual USD/Bs conversion rate. | ES: Tasa de conversión manual USD/Bs.",
    )
    l10n_ve_ta_multicurrency_prev_currency_id = fields.Many2one('res.currency', string="Prev Currency")
    l10n_ve_ta_multicurrency_prev_manual_rate = fields.Float(string="Prev Rate", digits=(16, 4))
    
    l10n_ve_ta_multicurrency_applied_rate = fields.Float(
        string='Tasa Aplicada',
        compute='_compute_l10n_ve_ta_multicurrency_applied_rate',
        digits=(12, 4),
        store=True,
    )

    l10n_ve_ta_multicurrency_summary_title = fields.Char(
        compute='_compute_l10n_ve_ta_multicurrency_summary_title',
    )

    l10n_ve_ta_multicurrency_show_summary = fields.Boolean(
        compute='_compute_l10n_ve_ta_multicurrency_show_summary',
    )

    @api.depends('l10n_ve_ta_multicurrency_use_manual_rate', 'l10n_ve_ta_multicurrency_rate', 'date_order', 'currency_id', 'company_id', 'l10n_ve_ta_multicurrency_fiscal_id')
    def _compute_l10n_ve_ta_multicurrency_applied_rate(self):
        """
        Calcula la tasa efectiva expresada siempre de forma que sea >= 1.0
        para evitar que el redondeo a 2 decimales la convierta en 0.00.
        """
        for order in self:
            if order.l10n_ve_ta_multicurrency_use_manual_rate and order.l10n_ve_ta_multicurrency_rate > 0:
                target_currency = order.l10n_ve_ta_multicurrency_fiscal_id
                operation = target_currency.l10n_ve_ta_multicurrency_operation or 'multiply' if target_currency else 'multiply'
                if operation == 'divide':
                    val = 1.0 / order.l10n_ve_ta_multicurrency_rate
                else:
                    val = order.l10n_ve_ta_multicurrency_rate
                order.l10n_ve_ta_multicurrency_applied_rate = val if val >= 1.0 else 1.0 / val
            else:
                company_currency = order.company_id.currency_id
                target_currency = order.l10n_ve_ta_multicurrency_fiscal_id
                doc_currency = order.currency_id

                if not company_currency or not target_currency or not doc_currency:
                    order.l10n_ve_ta_multicurrency_applied_rate = 1.0
                else:
                    date = order.date_order or fields.Date.context_today(order)
                    try:
                        rate = doc_currency._get_conversion_rate(
                            doc_currency, target_currency, order.company_id, date
                        )
                        if not rate:
                            rate = company_currency._get_conversion_rate(
                                company_currency, target_currency, order.company_id, date
                            )
                        if not rate:
                            order.l10n_ve_ta_multicurrency_applied_rate = 1.0
                        else:
                            operation = target_currency.l10n_ve_ta_multicurrency_operation or 'multiply'
                            if operation == 'divide':
                                rate = 1.0 / rate if rate > 0 else 1.0
                            order.l10n_ve_ta_multicurrency_applied_rate = rate if rate >= 1.0 else 1.0 / rate
                    except Exception:
                        order.l10n_ve_ta_multicurrency_applied_rate = 1.0

    @api.depends('l10n_ve_ta_multicurrency_fiscal_id', 'l10n_ve_ta_multicurrency_applied_rate')
    def _compute_l10n_ve_ta_multicurrency_summary_title(self):
        for order in self:
            currency_name = order.l10n_ve_ta_multicurrency_fiscal_id.name or ''
            rate_val = order.l10n_ve_ta_multicurrency_applied_rate or 1.0
            formatted_rate = "{:,.4f}".format(rate_val).replace(",", "X").replace(".", ",").replace("X", ".")
            order.l10n_ve_ta_multicurrency_summary_title = f"Referencia de {currency_name} (Tasa: {formatted_rate})"

    @api.depends('company_id')
    def _compute_l10n_ve_ta_multicurrency_show_summary(self):
        """
        EN: Always show the fiscal summary panel for purchase orders.
        ES: Siempre muestra el panel fiscal para órdenes de compra.
        """
        for order in self:
            order.l10n_ve_ta_multicurrency_show_summary = True


    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        string='Ref. Currency',
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )

    l10n_ve_ta_multicurrency_taxable_amount = fields.Float(
        string='Gravable Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Taxable base amount in reference currency. | ES: Base gravable en la moneda de referencia.",
    )
    l10n_ve_ta_multicurrency_exempt_amount = fields.Float(
        string='Monto Exento Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Exempt total amount in reference currency. | ES: Monto exento total en la moneda de referencia.",
    )
    l10n_ve_ta_multicurrency_discount_amount = fields.Float(
        string='Descuento Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Total discount calculated in reference currency. | ES: Descuento total calculado en la moneda de referencia.",
    )
    l10n_ve_ta_multicurrency_tax_amount = fields.Float(
        string='Impuesto Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Total tax amount in reference currency. | ES: Monto de impuesto total en la moneda de referencia.",
    )
    l10n_ve_ta_multicurrency_total_amount = fields.Float(
        string='Total Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Total order amount in reference currency. | ES: Monto total del presupuesto en la moneda de referencia.",
    )
    l10n_ve_ta_multicurrency_untaxed_amount = fields.Float(
        string='Subtotal Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Untaxed total amount in reference currency. | ES: Monto subtotal sin impuestos en la moneda de referencia.",
    )

    @api.depends('company_id', 'currency_id')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        Lógica Bimonetaria Estricta Dinámica:
        Determina la moneda de referencia (fiscal_id) basándose en la de la compañía.
        """
        for order in self:
            company_currency = order.company_id.currency_id
            if not company_currency:
                order.l10n_ve_ta_multicurrency_fiscal_id = False
                continue

            if order.currency_id == company_currency:
                foreign_curr = self.env['res.currency'].sudo().search([
                    ('id', '!=', company_currency.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
                order.l10n_ve_ta_multicurrency_fiscal_id = foreign_curr.id if foreign_curr else False
            else:
                order.l10n_ve_ta_multicurrency_fiscal_id = company_currency.id

    @api.depends(
        'order_line.price_subtotal',
        'order_line.price_tax',
        'order_line.price_total',
        'currency_id',
        'l10n_ve_ta_multicurrency_use_manual_rate',
        'l10n_ve_ta_multicurrency_rate',
        'l10n_ve_ta_multicurrency_fiscal_id',
        'date_order',
    )
    @api.depends(
        'order_line.l10n_ve_ta_multicurrency_taxable_amount',
        'order_line.l10n_ve_ta_multicurrency_exempt_amount',
        'order_line.l10n_ve_ta_multicurrency_discount_amount',
        'order_line.l10n_ve_ta_multicurrency_tax_amount',
        'order_line.l10n_ve_ta_multicurrency_total_amount',
        'l10n_ve_ta_multicurrency_fiscal_id',
        'l10n_ve_ta_multicurrency_rate',
        'l10n_ve_ta_multicurrency_use_manual_rate'
    )
    def _compute_l10n_ve_ta_multicurrency_fiscal_totals(self):
        """
        EN: Compute fiscal totals by summing up line-level amounts and converting using the rate.
        ES: Calcula los totales fiscales sumando los montos de línea y convirtiendo con la tasa.
        """
        for order in self:
            factor = order._get_l10n_ve_ta_multicurrency_factor()
            lines = order.order_line.filtered(lambda l: not l.display_type)

            sum_taxable = sum(lines.mapped('l10n_ve_ta_multicurrency_taxable_amount'))
            sum_exempt = sum(lines.mapped('l10n_ve_ta_multicurrency_exempt_amount'))
            sum_discount = sum(lines.mapped('l10n_ve_ta_multicurrency_discount_amount'))
            sum_tax = sum(lines.mapped('l10n_ve_ta_multicurrency_tax_amount'))
            line_total = sum(lines.mapped('l10n_ve_ta_multicurrency_total_amount'))
            sum_total = line_total if line_total else (order.amount_total or 0.0) * factor

            order.l10n_ve_ta_multicurrency_taxable_amount = sum_taxable
            order.l10n_ve_ta_multicurrency_exempt_amount  = sum_exempt
            order.l10n_ve_ta_multicurrency_discount_amount = sum_discount
            order.l10n_ve_ta_multicurrency_tax_amount     = sum_tax
            order.l10n_ve_ta_multicurrency_total_amount   = sum_total
            order.l10n_ve_ta_multicurrency_untaxed_amount = sum_taxable + sum_exempt

    def _compute_tax_totals(self):
        """
        EN: Override native totals to disable company currency conversion display.
        ES: Invalida los totales nativos para desactivar la visualización de la conversión a moneda de compañía.
        """
        super()._compute_tax_totals()
        for order in self:
            if order.tax_totals and isinstance(order.tax_totals, dict):
                # Ensure Odoo's native multicurrency conversion is hidden
                order.tax_totals['display_in_company_currency'] = False
                # Remove the parenthesized Total Ref from the dictionary added by Odoo 18 Purchase module
                if 'amount_total_cc' in order.tax_totals:
                    order.tax_totals['amount_total_cc'] = ''

    def _get_l10n_ve_ta_multicurrency_rate(self):
        """
        Retorna la tasa de cambio expresada como ref/base (unidades de moneda referencial
        por 1 unidad de moneda base). Usar _get_l10n_ve_ta_multicurrency_factor() para
        obtener el multiplicador direccional correcto según la moneda del documento.
        """
        self.ensure_one()
        target_currency = self.l10n_ve_ta_multicurrency_fiscal_id
        if not target_currency:
            return 1.0

        # Tasa manual
        if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0:
            operation = target_currency.l10n_ve_ta_multicurrency_operation or 'multiply'
            # op=multiply: usuario ingresó ref/base
            # op=divide:   usuario ingresó base/ref → convertimos a ref/base
            if operation == 'divide':
                return 1.0 / self.l10n_ve_ta_multicurrency_rate
            else:
                return self.l10n_ve_ta_multicurrency_rate

        # Tasa automática (BCV): base → referencial
        company_currency = self.company_id.currency_id
        date = self.date_order or fields.Date.context_today(self)
        try:
            rate = company_currency._get_conversion_rate(
                company_currency, target_currency, self.company_id, date
            )
            return rate or 1.0
        except Exception:
            return 1.0

    def _get_l10n_ve_ta_multicurrency_factor(self):
        """
        Factor directo: factor × monto_documento = monto_referencia.
        Calcula usando la tasa raw de conversión doc→ref para determinar
        la dirección correcta sin importar cuál es la moneda base.
        """
        self.ensure_one()
        doc_currency = self.currency_id
        ref_currency = self.l10n_ve_ta_multicurrency_fiscal_id

        if not doc_currency or not ref_currency or doc_currency == ref_currency:
            return 1.0

        company = self.company_id
        if not company or not company.currency_id:
            return 1.0

        rate_date = self.date_order or fields.Date.context_today(self)

        # Obtener tasa raw doc → ref (el factor real de conversión)
        try:
            raw_rate = doc_currency._get_conversion_rate(
                doc_currency, ref_currency, company, rate_date
            )
        except Exception:
            raw_rate = 1.0
        if not raw_rate or raw_rate <= 0:
            raw_rate = 1.0

        # Si hay tasa manual, usarla respetando la dirección
        if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0:
            manual_rate = self.l10n_ve_ta_multicurrency_rate
            if raw_rate >= 1.0:
                return manual_rate
            else:
                return 1.0 / manual_rate if manual_rate > 0 else 1.0

        return raw_rate

    @api.onchange('currency_id', 'l10n_ve_ta_multicurrency_use_manual_rate', 'l10n_ve_ta_multicurrency_rate')
    def _onchange_l10n_ve_ta_multicurrency_translate_prices(self):
        """
        EN: Convert existing line prices when switching currency to ensure consistent pricing.
        ES: Convierte los precios de las líneas existentes al cambiar de moneda para mantener consistencia.
        """
        prev_currency = self.l10n_ve_ta_multicurrency_prev_currency_id
        new_currency = self.currency_id
        if prev_currency and new_currency and prev_currency != new_currency:
            rate_date = self.date_order or fields.Date.context_today(self)
            try:
                if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0:
                    if prev_currency.name == 'USD' and new_currency.name in ('VES', 'VEF', 'VEB'):
                        rate = self.l10n_ve_ta_multicurrency_rate
                    elif prev_currency.name in ('VES', 'VEF', 'VEB') and new_currency.name == 'USD':
                        rate = 1.0 / self.l10n_ve_ta_multicurrency_rate
                    else:
                        rate = prev_currency._get_conversion_rate(prev_currency, new_currency, self.company_id, rate_date)
                else:
                    rate = prev_currency._get_conversion_rate(prev_currency, new_currency, self.company_id, rate_date)
            except Exception:
                rate = 1.0

            if rate and rate != 1.0:
                for line in self.order_line:
                    if line.price_unit:
                        line.price_unit = line.price_unit * rate

        self.l10n_ve_ta_multicurrency_prev_currency_id = self.currency_id
        self.l10n_ve_ta_multicurrency_prev_manual_rate = (
            self.l10n_ve_ta_multicurrency_rate
            if self.l10n_ve_ta_multicurrency_use_manual_rate
            else 0.0
        )

    def _prepare_invoice(self):
        """
        EN: Transfer custom exchange rate settings to the invoice when created from a purchase order.
        ES: Transfiere la configuración de tasa de cambio a la factura al ser creada desde una orden de compra.
        """
        invoice_vals = super()._prepare_invoice()
        invoice_vals.update({
            'l10n_ve_ta_multicurrency_use_manual_rate': self.l10n_ve_ta_multicurrency_use_manual_rate,
            'l10n_ve_ta_multicurrency_rate': self.l10n_ve_ta_multicurrency_rate,
        })
        return invoice_vals


class PurchaseOrderLine(models.Model):
    """
    EN: Extend purchase.order.line with bimonetary fiscal amounts.
    ES: Extiende purchase.order.line con montos fiscales bimonetarios.
    """
    _inherit = 'purchase.order.line'

    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        string='Ref. Currency',
        related='order_id.l10n_ve_ta_multicurrency_fiscal_id',
    )

    @api.onchange('product_id')
    def _onchange_product_id_l10n_ve_ta_multicurrency_hook(self):
        """
        EN: Onchange on product_id to apply our custom bimonetary rate.
            Calls super() safely in case the parent defines the method.
        ES: Onchange en product_id para aplicar la tasa bimonetaria.
            Llama a super() de forma segura por si el padre define el método.
        """
        if hasattr(super(), '_onchange_product_id'):
            super()._onchange_product_id()
        self._onchange_product_id_l10n_ve_ta_multicurrency()

    def _onchange_product_id_l10n_ve_ta_multicurrency(self):
        """
        EN: Adjust price_unit proportionally ONLY when a manual rate is active.
        ES: Ajusta price_unit proporcionalmente SOLO cuando una tasa manual está activa.
        """
        if not self.product_id or not self.order_id:
            return

        if self.order_id.l10n_ve_ta_multicurrency_use_manual_rate and self.order_id.l10n_ve_ta_multicurrency_rate > 0:
            company_currency = self.order_id.company_id.currency_id
            if company_currency and self.order_id.currency_id != company_currency:
                rate_date = self.order_id.date_order or fields.Date.context_today(self)
                try:
                    conv_rate = company_currency._get_conversion_rate(
                        company_currency, self.order_id.currency_id, self.order_id.company_id, rate_date
                    )
                except Exception:
                    conv_rate = 1.0
                if conv_rate:
                    manual_factor = (1.0 / self.order_id.l10n_ve_ta_multicurrency_rate) / conv_rate
                    self.price_unit = self.price_unit * manual_factor

    l10n_ve_ta_multicurrency_price_unit = fields.Float(
        string='Unit Price Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
        store=True,
    )
    l10n_ve_ta_multicurrency_taxable_amount = fields.Float(
        string='Taxable Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
        store=True,
    )
    l10n_ve_ta_multicurrency_exempt_amount = fields.Float(
        string='Exempt Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
        store=True,
    )
    l10n_ve_ta_multicurrency_discount_amount = fields.Float(
        string='Discount Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
        store=True,
    )
    l10n_ve_ta_multicurrency_tax_amount = fields.Float(
        string='Tax Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
        store=True,
    )
    l10n_ve_ta_multicurrency_total_amount = fields.Float(
        string='Total Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
        store=True,
    )

    # ---- Per-line fields in DOCUMENT CURRENCY ----
    l10n_ve_ta_multicurrency_taxable_amount_curr = fields.Monetary(
        string='Gravable',
        currency_field='l10n_ve_ta_multicurrency_order_currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
    )
    l10n_ve_ta_multicurrency_exempt_amount_curr = fields.Monetary(
        string='Exento',
        currency_field='l10n_ve_ta_multicurrency_order_currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
    )
    l10n_ve_ta_multicurrency_tax_amount_curr = fields.Monetary(
        string='Impuesto',
        currency_field='l10n_ve_ta_multicurrency_order_currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_line_amounts',
    )
    l10n_ve_ta_multicurrency_order_currency_id = fields.Many2one(
        'res.currency',
        string='Order Currency',
        related='order_id.currency_id',
        store=False,
    )

    @api.depends(
        'price_subtotal',
        'price_tax',
        'price_total',
        'display_type',
        'order_id.currency_id',
        'order_id.l10n_ve_ta_multicurrency_rate',
        'order_id.l10n_ve_ta_multicurrency_use_manual_rate',
        'order_id.l10n_ve_ta_multicurrency_applied_rate',
    )
    def _compute_l10n_ve_ta_multicurrency_line_amounts(self):
        """
        Calcula los montos fiscales por línea en la moneda de referencia.
        Usa el factor dinámico (Inverse Calculation) para convertir correctamente
        sin importar si el documento está en la moneda base o referencial.
        """
        for line in self:
            if line.display_type:
                line.l10n_ve_ta_multicurrency_taxable_amount = 0.0
                line.l10n_ve_ta_multicurrency_exempt_amount = 0.0
                line.l10n_ve_ta_multicurrency_price_unit = 0.0
                line.l10n_ve_ta_multicurrency_discount_amount = 0.0
                line.l10n_ve_ta_multicurrency_tax_amount = 0.0
                line.l10n_ve_ta_multicurrency_total_amount = 0.0
                line.l10n_ve_ta_multicurrency_taxable_amount_curr = 0.0
                line.l10n_ve_ta_multicurrency_exempt_amount_curr = 0.0
                line.l10n_ve_ta_multicurrency_tax_amount_curr = 0.0
                continue

            # factor: multiplicador para convertir montos del doc a la moneda referencial
            # Inverse Calculation: si doc está en base → factor=rate; si en referencial → factor=1/rate
            factor = line.order_id._get_l10n_ve_ta_multicurrency_factor()
            subtotal = (line.price_subtotal or 0.0) * factor
            total = (line.price_total or 0.0) * factor
            price_unit = (line.price_unit or 0.0) * factor
            is_exempt = not bool(line.taxes_id)

            line.l10n_ve_ta_multicurrency_price_unit = price_unit
            line.l10n_ve_ta_multicurrency_taxable_amount = subtotal if not is_exempt else 0.0
            line.l10n_ve_ta_multicurrency_exempt_amount = subtotal if is_exempt else 0.0

            # Nominal price before discount
            nominal = (line.product_qty or 0.0) * price_unit
            line.l10n_ve_ta_multicurrency_discount_amount = max(nominal - subtotal, 0.0)

            line.l10n_ve_ta_multicurrency_tax_amount = (line.price_tax or 0.0) * factor
            line.l10n_ve_ta_multicurrency_total_amount = total

            # Document currency fields (sin conversión, moneda del propio documento)
            line.l10n_ve_ta_multicurrency_taxable_amount_curr = line.price_subtotal if not is_exempt else 0.0
            line.l10n_ve_ta_multicurrency_exempt_amount_curr = line.price_subtotal if is_exempt else 0.0
            line.l10n_ve_ta_multicurrency_tax_amount_curr = line.price_tax or 0.0
