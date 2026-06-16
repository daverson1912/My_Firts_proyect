from odoo import models, fields, api, _


import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def _calculate_total_retention(self):
        self.ensure_one()
        if not self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic():
            return super()._calculate_total_retention()
        
        total_retention = 0.0
        for line in self.line_ids:
            if line.tax_line_id:
                tax = line.tax_line_id
                if (hasattr(tax, 'is_simplit_tax') and tax.is_simplit_tax) or getattr(tax, 'simplit_tax_type', False):
                    if tax.amount < 0:
                        total_retention += abs(line.amount_currency)
        return total_retention

    def _calculate_tax_base(self):
        self.ensure_one()
        if not self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic():
            return super()._calculate_tax_base()
            
        total_tax = 0.0
        for line in self.line_ids:
            if line.tax_line_id:
                tax = line.tax_line_id
                if tax.amount > 0:
                    total_tax += abs(line.amount_currency)
        return total_tax

    l10n_ve_ta_multicurrency_use_manual_rate = fields.Boolean(
        string='Use Manual Rate',
        default=False,
        help='EN: Mark to manually enter the exchange rate. | ES: Marque para ingresar manualmente la tasa de cambio.',
    )

    l10n_ve_ta_multicurrency_rate = fields.Float(
        string='Exchange Rate',
        digits=(12, 6),
        default=0.0,
        help='EN: Manual conversion rate (Bs/USD). | ES: Tasa de conversión manual (Bs/USD).',
    )

    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        string='Ref. Currency',
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )

    l10n_ve_ta_multicurrency_summary_title = fields.Char(
        compute='_compute_l10n_ve_ta_multicurrency_summary_title',
    )

    l10n_ve_ta_multicurrency_show_summary = fields.Boolean(
        compute='_compute_l10n_ve_ta_multicurrency_show_summary',
    )

    l10n_ve_ta_multicurrency_enable_fiscal = fields.Boolean(
        string='Integración Fiscal Activa',
        compute='_compute_l10n_ve_ta_multicurrency_enable_fiscal'
    )

    # ---- Placeholders para campos de l10n_ve_simplit_fiscal (account.move) ----
    l10n_ve_islr_amount = fields.Monetary(string='Retención ISLR')
    l10n_ve_control_number = fields.Char(string='Nro de Control')
    l10n_ve_supplier_invoice_number = fields.Char(string='Nro Factura Proveedor')
    l10n_ve_has_igtf = fields.Boolean(string='Maneja IGTF')
    l10n_ve_igtf_amount = fields.Monetary(string='Monto IGTF')
    l10n_ve_igtf_base = fields.Monetary(string='Base IGTF')
    l10n_ve_fiscal_invoice_number = fields.Char(string='Nro Factura Fiscal')
    l10n_ve_fiscal_z_number = fields.Char(string='Nro de Reporte Z')
    l10n_ve_fiscal_printer_serial = fields.Char(string='Serial Impresora Fiscal')

    def _compute_l10n_ve_ta_multicurrency_enable_fiscal(self):
        for move in self:
            config = self.env['l10n_ve_ta_multicurrency.api.config'].sudo().search([
                ('company_id', '=', move.company_id.id),
                ('active', '=', True)
            ], limit=1)
            move.l10n_ve_ta_multicurrency_enable_fiscal = config.l10n_ve_ta_multicurrency_enable_fiscal if config else False
    
    
    l10n_ve_ta_multicurrency_applied_rate = fields.Float(
        string='Tasa Aplicada',
        compute='_compute_l10n_ve_ta_multicurrency_applied_rate',
        digits=(12, 4),
        store=True,
    )

    @api.depends('l10n_ve_ta_multicurrency_use_manual_rate', 'l10n_ve_ta_multicurrency_rate', 'invoice_date', 'date', 'currency_id', 'l10n_ve_ta_multicurrency_fiscal_id')
    def _compute_l10n_ve_ta_multicurrency_applied_rate(self):
        """
        Calcula la tasa de cambio efectiva. 
        Mantiene consistencia con la lógica de Activos y Préstamos de forma genérica.
        """
        for move in self:
            move.l10n_ve_ta_multicurrency_applied_rate = move._get_l10n_ve_ta_multicurrency_applied_rate_value()

    def _get_l10n_ve_ta_multicurrency_applied_rate_value(self):
        """
        Devuelve la tasa de cambio efectiva expresada siempre de forma que sea >= 1.0
        (por ejemplo, unidades de Bolívares por 1 unidad de USD) para evitar que
        el redondeo a 2 decimales en el campo float lo convierta en 0.00.
        """
        self.ensure_one()
        if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0:
            target_currency = self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            operation = target_currency.l10n_ve_ta_multicurrency_operation or 'multiply' if target_currency else 'multiply'
            if operation == 'divide':
                val = 1.0 / self.l10n_ve_ta_multicurrency_rate
            else:
                val = self.l10n_ve_ta_multicurrency_rate
            return val if val >= 1.0 else 1.0 / val

        target_currency = self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
        company_currency = self.company_id.currency_id
        doc_currency = self.currency_id

        if not target_currency or not company_currency or not doc_currency:
            return 1.0

        # Usar la moneda del documento como fuente para obtener la tasa hacia la moneda de referencia
        rate_date = self.invoice_date or self.date or fields.Date.context_today(self)
        rate = doc_currency._get_conversion_rate(
            doc_currency, target_currency, self.company_id, rate_date
        )
        # Si no hay tasa directa doc->ref, usa la tasa base->ref
        if not rate:
            rate = company_currency._get_conversion_rate(
                company_currency, target_currency, self.company_id, rate_date
            )
        if not rate:
            return 1.0

        operation = target_currency.l10n_ve_ta_multicurrency_operation or 'multiply'
        if operation == 'divide':
            rate = 1.0 / rate if rate > 0 else 1.0

        return rate if rate >= 1.0 else 1.0 / rate

    def _get_l10n_ve_ta_multicurrency_factor(self):
        """
        Factor directo: factor × monto_documento = monto_referencia.
        Calcula usando la tasa raw de conversión doc→ref para determinar
        la dirección correcta sin importar cuál es la moneda base.
        """
        self.ensure_one()
        doc_currency = self.currency_id
        ref_currency = self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()

        if not doc_currency or not ref_currency or doc_currency == ref_currency:
            return 1.0

        company = self.company_id
        if not company or not company.currency_id:
            return 1.0

        rate_date = self.invoice_date or self.date or fields.Date.context_today(self)

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
            # raw_rate indica la dirección natural:
            # >= 1: doc→ref escala hacia arriba (ej: USD→VEF), manual_rate reemplaza directamente
            # < 1: doc→ref escala hacia abajo (ej: VEF→USD), factor = 1/manual_rate
            if raw_rate >= 1.0:
                return manual_rate
            else:
                return 1.0 / manual_rate if manual_rate > 0 else 1.0

        return raw_rate

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
        help="EN: Total document amount in reference currency. | ES: Monto total del documento en la moneda de referencia.",
    )
    l10n_ve_ta_multicurrency_untaxed_amount = fields.Float(
        string='Subtotal Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_totals',
        store=True,
        help="EN: Untaxed total amount in reference currency. | ES: Monto subtotal sin impuestos en la moneda de referencia.",
    )

    # ---- Totales en moneda del DOCUMENTO (reemplazan tax_totals nativo) ----
    l10n_ve_ta_multicurrency_doc_taxable_amount = fields.Monetary(
        string='Gravable', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_exempt_amount = fields.Monetary(
        string='Exento', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_discount_amount = fields.Monetary(
        string='Descuento', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_subtotal = fields.Monetary(
        string='Subtotal', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_gross_iva = fields.Monetary(
        string='IVA', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_total = fields.Monetary(
        string='Total', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_ret_iva = fields.Monetary(
        string='Ret. IVA', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_ret_islr = fields.Monetary(
        string='Ret. ISLR', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_igtf = fields.Monetary(
        string='Impuesto IGTF', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )
    l10n_ve_ta_multicurrency_doc_amount_to_pay = fields.Monetary(
        string='Monto a Pagar', currency_field='currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_doc_amounts',
    )

    @api.depends(
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.price_total',
        'invoice_line_ids.price_unit',
        'invoice_line_ids.quantity',
        'invoice_line_ids.discount',
        'invoice_line_ids.tax_ids',
        'invoice_line_ids.display_type',
        'l10n_ve_islr_amount',
        'l10n_ve_igtf_amount',
        'currency_id',
        'partner_id',
        'l10n_ve_ta_multicurrency_fiscal_id',
        'l10n_ve_ta_multicurrency_applied_rate',
    )
    def _compute_l10n_ve_ta_multicurrency_doc_amounts(self):
        for move in self:
            lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')
            )
            taxable = exempt = discount = subtotal = gross_iva = net_total = 0.0

            for line in lines:
                ps = line.price_subtotal or 0.0
                pt = line.price_total or 0.0
                subtotal  += ps
                net_total += pt

                if line.tax_ids:
                    taxable += ps
                    # IVA bruto: solo impuestos POSITIVOS (excluye retenciones negativas)
                    tax_res = line.tax_ids.compute_all(
                        line.price_unit, move.currency_id,
                        line.quantity, product=line.product_id,
                        partner=move.partner_id,
                    )
                    gross_iva += sum(
                        t['amount'] for t in tax_res.get('taxes', []) if t['amount'] > 0
                    )
                else:
                    exempt += ps

                if line.discount:
                    nominal = (line.quantity or 0.0) * (line.price_unit or 0.0)
                    discount += max(nominal - ps, 0.0)

            # Total fiscal = subtotal + IVA bruto (900 + 144 = 1044)
            # Diferente al total Odoo (936) que ya tiene la ret. IVA descontada.
            total_fiscal = subtotal + gross_iva
            # IVA neto Odoo = net_total - subtotal = 936 - 900 = 36
            # Ret. IVA = IVA neto - IVA bruto = 36 - 144 = -108
            ret_iva = (net_total - subtotal) - gross_iva

            islr = getattr(move, 'l10n_ve_islr_amount', 0.0) or 0.0

            # doc_ret_islr: round-trip a través de la moneda de referencia para
            # garantizar que nativo × factor = referencia (cuadra en ambas direcciones).
            # Pasos: islr_native → × factor → redondear en ref_currency → ÷ factor
            # Ejemplo VEF: 14.966,50 × (1/554,4258) = 26,9946 → USD.round = 26,99
            #              → 26,99 ÷ (1/554,4258) = 26,99 × 554,4258 = 14.963,95 Bs
            # Ejemplo USD: 26,99 × 554,4258 = 14.963,95 → VEF.round = 14.963,95
            #              → 14.963,95 ÷ 554,4258 = 26,99 USD  (sin cambio)
            factor = move._get_l10n_ve_ta_multicurrency_factor()
            fiscal_curr = move.l10n_ve_ta_multicurrency_fiscal_id
            if islr and factor and factor > 0 and fiscal_curr:
                islr_ref_rounded = fiscal_curr.round(islr * factor)
                doc_ret_islr_val = islr_ref_rounded / factor
            else:
                doc_ret_islr_val = islr

            move.l10n_ve_ta_multicurrency_doc_taxable_amount  = taxable
            move.l10n_ve_ta_multicurrency_doc_exempt_amount   = exempt
            move.l10n_ve_ta_multicurrency_doc_discount_amount = discount
            move.l10n_ve_ta_multicurrency_doc_subtotal        = subtotal
            move.l10n_ve_ta_multicurrency_doc_gross_iva       = gross_iva
            move.l10n_ve_ta_multicurrency_doc_total           = total_fiscal
            doc_igtf = getattr(move, 'l10n_ve_igtf_amount', 0.0) or 0.0

            move.l10n_ve_ta_multicurrency_doc_ret_iva         = ret_iva
            move.l10n_ve_ta_multicurrency_doc_ret_islr        = -abs(doc_ret_islr_val) if doc_ret_islr_val else 0.0
            move.l10n_ve_ta_multicurrency_doc_igtf            = doc_igtf
            move.l10n_ve_ta_multicurrency_doc_amount_to_pay   = (
                total_fiscal + ret_iva
                + (-abs(doc_ret_islr_val) if doc_ret_islr_val else 0.0)
                - doc_igtf
            )

    l10n_ve_ta_multicurrency_retention_iva_amount = fields.Float(
        string='Retención IVA Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_retentions_ref',
        help="Monto de retención de IVA en moneda de referencia."
    )
    l10n_ve_ta_multicurrency_retention_islr_amount = fields.Float(
        string='Retención ISLR Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_retentions_ref',
        help="Monto de retención de ISLR en moneda de referencia."
    )
    l10n_ve_ta_multicurrency_igtf_amount = fields.Float(
        string='IGTF Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_retentions_ref',
        help="Proyección del IGTF (3%) en moneda de referencia."
    )
    l10n_ve_ta_multicurrency_amount_to_pay = fields.Float(
        string='Neto a Pagar Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_retentions_ref',
        help="Monto neto a pagar (Total - Retenciones) en moneda de referencia."
    )

    l10n_ve_ta_multicurrency_show_retention_iva = fields.Boolean(
        string='Mostrar Retención IVA',
        compute='_compute_l10n_ve_ta_show_retention_fields'
    )
    l10n_ve_ta_multicurrency_show_retention_islr = fields.Boolean(
        string='Mostrar Retención ISLR',
        compute='_compute_l10n_ve_ta_show_retention_fields'
    )
    l10n_ve_ta_multicurrency_show_amount_to_pay = fields.Boolean(
        string='Mostrar Cantidad por Pagar',
        compute='_compute_l10n_ve_ta_show_retention_fields'
    )
    l10n_ve_ta_multicurrency_show_total_amount = fields.Boolean(
        string='Mostrar Total',
        compute='_compute_l10n_ve_ta_show_retention_fields'
    )

    @api.depends(
        'l10n_ve_ta_multicurrency_total_amount', 
        'line_ids.tax_line_id', 
        'line_ids.amount_currency',
        'l10n_ve_ta_multicurrency_applied_rate',
        'tax_totals',
        'invoice_line_ids.l10n_ve_islr_amount_line_ref',
        'l10n_ve_islr_amount'
    )
    def _compute_l10n_ve_ta_multicurrency_retentions_ref(self):
        """
        Calcula el desglose de retenciones y el neto a pagar en la moneda de referencia.
        Prioriza los montos de los comprobantes fiscales si la integración está activa.
        NOTA: Usar amount_currency (moneda documento) en vez de balance (moneda compañía)
        porque el factor convierte doc→ref, no company→ref.
        """
        for move in self:
            config = self.env['l10n_ve_ta_multicurrency.api.config'].sudo().search([
                ('company_id', '=', move.company_id.id),
                ('active', '=', True)
            ], limit=1)
            enable_fiscal = config.l10n_ve_ta_multicurrency_enable_fiscal if config else False

            factor = move._get_l10n_ve_ta_multicurrency_factor()
            fiscal_currency = move._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            
            # --- 1. Retención IVA ---
            iva_ret_ref = 0.0
            if enable_fiscal and 'account.wh.iva' in self.env:
                wh_iva = self.env['account.wh.iva'].sudo().search([('move_id', '=', move.id), ('state', '!=', 'cancel')], limit=1)
                if wh_iva:
                    # Seleccionar el monto en la moneda de referencia de la factura de forma robusta
                    if wh_iva.currency_id == fiscal_currency:
                        iva_ret_ref = wh_iva.amount_total_ret
                    elif wh_iva.l10n_ve_ta_multicurrency_fiscal_id == fiscal_currency:
                        iva_ret_ref = wh_iva.l10n_ve_ta_multicurrency_amount_total_ret
                    else:
                        try:
                            rate_date = move.invoice_date or move.date or fields.Date.context_today(move)
                            conv_rate = wh_iva.currency_id._get_conversion_rate(
                                wh_iva.currency_id, fiscal_currency, move.company_id, rate_date
                            )
                            iva_ret_ref = wh_iva.amount_total_ret * conv_rate
                        except Exception:
                            iva_ret_ref = wh_iva.amount_total_ret
                else:
                    # Intentar obtener de tax_totals primero (en la moneda del documento)
                    iva_ret_curr = 0.0
                    if move.tax_totals and isinstance(move.tax_totals, dict):
                        for subtotal in move.tax_totals.get('subtotals', []):
                            for group in subtotal.get('tax_groups', []):
                                g_name = group.get('group_name', '')
                                if g_name and ('Retención IVA' in g_name or 'Ret. IVA' in g_name or 'retencion iva' in g_name.lower()):
                                    iva_ret_curr += abs(group.get('tax_amount_currency', 0.0))
                    
                    if iva_ret_curr > 0:
                        iva_ret_ref = iva_ret_curr * factor
                    else:
                        # Fallback a balance contable si no está en tax_totals
                        total_ret_iva_vef = sum(abs(l.balance) for l in move.line_ids.filtered(
                            lambda l: l.tax_line_id and (
                                l.tax_line_id.amount < 0 or 
                                getattr(l.tax_line_id, 'is_retention', False) or 
                                'retencion' in (l.tax_line_id.name or '').lower() or
                                'ret.iva' in (l.name or '').lower() or
                                'retencion iva' in (l.name or '').lower()
                            )
                        ))
                        if fiscal_currency.name == 'USD':
                            iva_ret_ref = total_ret_iva_vef  # balance ya está en USD (moneda compañía = fiscal)
                        else:
                            company_currency = move.company_id.currency_id
                            ref_currency = fiscal_currency
                            if company_currency != ref_currency:
                                rate_date = move.invoice_date or move.date or fields.Date.context_today(move)
                                try:
                                    conv_rate = company_currency._get_conversion_rate(
                                        company_currency, ref_currency, move.company_id, rate_date
                                    )
                                    iva_ret_ref = total_ret_iva_vef * conv_rate
                                except Exception:
                                    iva_ret_ref = total_ret_iva_vef
                            else:
                                iva_ret_ref = total_ret_iva_vef
            else:
                iva_ret_curr = 0.0
                if move.tax_totals and isinstance(move.tax_totals, dict):
                    for subtotal in move.tax_totals.get('subtotals', []):
                        for group in subtotal.get('tax_groups', []):
                            g_name = group.get('group_name', '')
                            if g_name and ('Retención IVA' in g_name or 'Ret. IVA' in g_name or 'retencion iva' in g_name.lower()):
                                iva_ret_curr += abs(group.get('tax_amount_currency', 0.0))
                
                if iva_ret_curr > 0:
                    iva_ret_ref = iva_ret_curr * factor
                else:
                    total_ret_iva_vef = sum(abs(l.balance) for l in move.line_ids.filtered(
                        lambda l: l.tax_line_id and (
                            l.tax_line_id.amount < 0 or 
                            getattr(l.tax_line_id, 'is_retention', False) or 
                            'retencion' in (l.tax_line_id.name or '').lower() or
                            'ret.iva' in (l.name or '').lower() or
                            'retencion iva' in (l.name or '').lower()
                        )
                    ))
                    if fiscal_currency.name == 'USD':
                        iva_ret_ref = total_ret_iva_vef  # balance ya está en USD (moneda compañía = fiscal)
                    else:
                        company_currency = move.company_id.currency_id
                        ref_currency = fiscal_currency
                        if company_currency != ref_currency:
                            rate_date = move.invoice_date or move.date or fields.Date.context_today(move)
                            try:
                                conv_rate = company_currency._get_conversion_rate(
                                    company_currency, ref_currency, move.company_id, rate_date
                                )
                                iva_ret_ref = total_ret_iva_vef * conv_rate
                            except Exception:
                                iva_ret_ref = total_ret_iva_vef
                        else:
                            iva_ret_ref = total_ret_iva_vef

            move.l10n_ve_ta_multicurrency_retention_iva_amount = -abs(iva_ret_ref) if iva_ret_ref else 0.0

            # --- 2. Retención ISLR ---
            islr_ret_ref = 0.0
            # Retención ISLR en moneda de referencia.
            # Se deriva siempre desde l10n_ve_islr_amount × factor para garantizar
            # consistencia con la sección nativa (ambas cuadran al tipo de cambio).
            # Fuente prioritaria: account.wh.islr si existe.
            if enable_fiscal and 'account.wh.islr' in self.env:
                wh_islr = self.env['account.wh.islr'].sudo().search([('move_id', '=', move.id), ('state', '!=', 'cancel')], limit=1)
                if wh_islr:
                    if wh_islr.currency_id == fiscal_currency:
                        islr_ret_ref = wh_islr.amount_total_ret
                    elif wh_islr.l10n_ve_ta_multicurrency_fiscal_id == fiscal_currency:
                        islr_ret_ref = wh_islr.l10n_ve_ta_multicurrency_amount_total_ret
                    else:
                        try:
                            rate_date = move.invoice_date or move.date or fields.Date.context_today(move)
                            conv_rate = wh_islr.currency_id._get_conversion_rate(
                                wh_islr.currency_id, fiscal_currency, move.company_id, rate_date
                            )
                            islr_ret_ref = wh_islr.amount_total_ret * conv_rate
                        except Exception:
                            islr_ret_ref = getattr(move, 'l10n_ve_islr_amount', 0.0) * factor
                else:
                    islr_ret_ref = getattr(move, 'l10n_ve_islr_amount', 0.0) * factor
            else:
                islr_ret_ref = getattr(move, 'l10n_ve_islr_amount', 0.0) * factor

            move.l10n_ve_ta_multicurrency_retention_islr_amount = -abs(islr_ret_ref) if islr_ret_ref else 0.0

            # --- 3. IGTF (Proyectado) ---
            move.l10n_ve_ta_multicurrency_igtf_amount = getattr(move, 'l10n_ve_igtf_amount', 0.0) * factor

            # --- 4. Neto a Pagar ---
            # Fórmula: Total + Ret.IVA (neg) + Ret.ISLR (neg) - IGTF
            # ret_iva y ret_islr ya son negativos; igtf solo aplica en ventas.
            if fiscal_currency:
                move.l10n_ve_ta_multicurrency_retention_iva_amount = fiscal_currency.round(move.l10n_ve_ta_multicurrency_retention_iva_amount)
                move.l10n_ve_ta_multicurrency_retention_islr_amount = fiscal_currency.round(move.l10n_ve_ta_multicurrency_retention_islr_amount)
                move.l10n_ve_ta_multicurrency_igtf_amount = fiscal_currency.round(move.l10n_ve_ta_multicurrency_igtf_amount)

                untaxed  = move.l10n_ve_ta_multicurrency_untaxed_amount
                tax      = move.l10n_ve_ta_multicurrency_tax_amount
                ret_iva  = move.l10n_ve_ta_multicurrency_retention_iva_amount   # negativo
                ret_islr = move.l10n_ve_ta_multicurrency_retention_islr_amount  # negativo
                igtf     = move.l10n_ve_ta_multicurrency_igtf_amount            # positivo (solo ventas)

                move.l10n_ve_ta_multicurrency_amount_to_pay = fiscal_currency.round(
                    untaxed + tax + ret_iva + ret_islr - igtf
                )
            else:
                move.l10n_ve_ta_multicurrency_amount_to_pay = (
                    move.l10n_ve_ta_multicurrency_untaxed_amount +
                    move.l10n_ve_ta_multicurrency_tax_amount +
                    move.l10n_ve_ta_multicurrency_retention_iva_amount +
                    move.l10n_ve_ta_multicurrency_retention_islr_amount -
                    move.l10n_ve_ta_multicurrency_igtf_amount
                )

    @api.depends(
        'l10n_ve_ta_multicurrency_retention_iva_amount',
        'l10n_ve_ta_multicurrency_retention_islr_amount',
        'l10n_ve_ta_multicurrency_fiscal_id',
        'l10n_ve_has_igtf',
        'move_type',
    )
    def _compute_l10n_ve_ta_show_retention_fields(self):
        for move in self:
            fiscal_currency = move._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            if fiscal_currency:
                show_iva = not fiscal_currency.is_zero(move.l10n_ve_ta_multicurrency_retention_iva_amount)
                show_islr = not fiscal_currency.is_zero(move.l10n_ve_ta_multicurrency_retention_islr_amount)
            else:
                show_iva = abs(move.l10n_ve_ta_multicurrency_retention_iva_amount) > 0.0001
                show_islr = abs(move.l10n_ve_ta_multicurrency_retention_islr_amount) > 0.0001

            show_igtf = (
                getattr(move, 'l10n_ve_has_igtf', False)
                and move.move_type in ('out_invoice', 'out_refund')
            )

            move.l10n_ve_ta_multicurrency_show_retention_iva = show_iva
            move.l10n_ve_ta_multicurrency_show_retention_islr = show_islr
            move.l10n_ve_ta_multicurrency_show_amount_to_pay = show_iva or show_islr or show_igtf
            move.l10n_ve_ta_multicurrency_show_total_amount = True  # siempre visible

    # Asset-related multicurrency fields
    l10n_ve_ta_multicurrency_depreciation_value_ref = fields.Float(
        string="Depreciation Ref.",
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_asset_ref_fields',
    )
    l10n_ve_ta_multicurrency_asset_depreciated_value_ref = fields.Float(
        string="Accumulated Depreciation Ref.",
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_asset_ref_fields',
    )
    l10n_ve_ta_multicurrency_asset_remaining_value_ref = fields.Float(
        string="Depreciable Value Ref.",
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_asset_ref_fields',
    )

    @api.depends(
        'depreciation_value', 
        'asset_depreciated_value', 
        'asset_remaining_value', 
        'l10n_ve_ta_multicurrency_applied_rate'
    )
    def _compute_l10n_ve_ta_multicurrency_asset_ref_fields(self):
        for move in self:
            rate = move.l10n_ve_ta_multicurrency_applied_rate or 1.0
            fiscal_currency = move._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            
            # Usar factor directo (doc → ref) que ya maneja la dirección correcta
            factor = move._get_l10n_ve_ta_multicurrency_factor()
            move.l10n_ve_ta_multicurrency_depreciation_value_ref = move.depreciation_value * factor
            move.l10n_ve_ta_multicurrency_asset_depreciated_value_ref = move.asset_depreciated_value * factor
            move.l10n_ve_ta_multicurrency_asset_remaining_value_ref = move.asset_remaining_value * factor


    @api.depends('currency_id')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        Lógica Bimonetaria Estricta Dinámica:
        Determina la moneda de referencia (fiscal_id) basándose en la de la compañía.
        """
        for move in self:
            company_currency = move.company_id.currency_id
            if not company_currency:
                move.l10n_ve_ta_multicurrency_fiscal_id = False
                continue
                
            move_is_company_curr = (move.currency_id == company_currency)
            
            if move_is_company_curr:
                # Si el documento está en la moneda de la compañía, la de referencia es la primera moneda extranjera activa
                foreign_curr = self.env['res.currency'].sudo().search([
                    ('id', '!=', company_currency.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
                move.l10n_ve_ta_multicurrency_fiscal_id = foreign_curr.id if foreign_curr else False
            else:
                # Si el documento no está en la moneda de la compañía, la de referencia es la de la compañía
                move.l10n_ve_ta_multicurrency_fiscal_id = company_currency.id

    def _get_l10n_ve_ta_multicurrency_fiscal_id_dynamic(self):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if not company_currency:
            return self.env['res.currency']
            
        move_is_company_curr = (self.currency_id == company_currency)
        if move_is_company_curr:
            foreign_curr = self.env['res.currency'].sudo().search([
                ('id', '!=', company_currency.id),
                ('active', '=', True)
            ], order='name asc', limit=1)
            return foreign_curr or self.env['res.currency']
        else:
            return company_currency

    @api.depends('l10n_ve_ta_multicurrency_fiscal_id', 'l10n_ve_ta_multicurrency_applied_rate')
    def _compute_l10n_ve_ta_multicurrency_summary_title(self):
        for move in self:
            currency_name = move._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic().name or ''
            rate_val = move.l10n_ve_ta_multicurrency_applied_rate or 1.0
            formatted_rate = "{:,.4f}".format(rate_val).replace(",", "X").replace(".", ",").replace("X", ".")
            move.l10n_ve_ta_multicurrency_summary_title = f"Referencia de {currency_name} (Tasa: {formatted_rate})"

    @api.depends('currency_id', 'l10n_ve_ta_multicurrency_fiscal_id', 'move_type')
    def _compute_l10n_ve_ta_multicurrency_show_summary(self):
        """
        EN: Decide whether to show the fiscal multicurrency panel.
        ES: Decide si mostrar el panel fiscal multidivisa.
        """
        for move in self:
            move.l10n_ve_ta_multicurrency_show_summary = move.move_type in (
                'out_invoice', 'out_refund', 'in_invoice', 'in_refund'
            )

    @api.depends(
        'invoice_line_ids.l10n_ve_ta_multicurrency_taxable_amount',
        'invoice_line_ids.l10n_ve_ta_multicurrency_exempt_amount',
        'invoice_line_ids.l10n_ve_ta_multicurrency_discount_amount',
        'invoice_line_ids.l10n_ve_ta_multicurrency_tax_amount',
        'invoice_line_ids.l10n_ve_ta_multicurrency_total_amount',
        'line_ids.debit',
        'line_ids.credit',
        'l10n_ve_ta_multicurrency_fiscal_id',
        'l10n_ve_ta_multicurrency_applied_rate',
        'amount_total',
    )
    def _compute_l10n_ve_ta_multicurrency_fiscal_totals(self):
        """
        EN: Compute fiscal totals by summing up line-level amounts and converting using the rate.
        ES: Calcula los totales fiscales sumando los montos de línea y convirtiendo con la tasa.
        """
        for move in self:
            factor = move._get_l10n_ve_ta_multicurrency_factor()
            if move.move_type != 'entry':
                # Invoice summation
                lines = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
                sum_taxable = sum(lines.mapped('l10n_ve_ta_multicurrency_taxable_amount'))
                sum_exempt = sum(lines.mapped('l10n_ve_ta_multicurrency_exempt_amount'))
                sum_discount = sum(lines.mapped('l10n_ve_ta_multicurrency_discount_amount'))
                sum_tax = sum(lines.mapped('l10n_ve_ta_multicurrency_tax_amount'))
                # Total Ref se basa en las líneas ya expresadas en moneda fiscal; si está vacío, usar neto * factor
                line_total = sum(lines.mapped('l10n_ve_ta_multicurrency_total_amount'))
                sum_total = line_total if line_total else (move.amount_total or 0.0) * factor
            else:
                # Direct entry summation (Miscellaneous)
                sum_taxable = sum_exempt = sum_discount = sum_tax = 0.0
                sum_total = sum(move.line_ids.mapped('debit'))

            # Sum up line-level amounts which are already in the fiscal target currency.
            curr = move._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            if curr:
                move.l10n_ve_ta_multicurrency_taxable_amount = curr.round(sum_taxable)
                move.l10n_ve_ta_multicurrency_exempt_amount  = curr.round(sum_exempt)
                move.l10n_ve_ta_multicurrency_discount_amount = curr.round(sum_discount)
                move.l10n_ve_ta_multicurrency_tax_amount     = curr.round(sum_tax)
                move.l10n_ve_ta_multicurrency_total_amount   = curr.round(sum_total)
                move.l10n_ve_ta_multicurrency_untaxed_amount = curr.round(sum_taxable + sum_exempt)
            else:
                move.l10n_ve_ta_multicurrency_taxable_amount = sum_taxable
                move.l10n_ve_ta_multicurrency_exempt_amount  = sum_exempt
                move.l10n_ve_ta_multicurrency_discount_amount = sum_discount
                move.l10n_ve_ta_multicurrency_tax_amount     = sum_tax
                move.l10n_ve_ta_multicurrency_total_amount   = sum_total
                move.l10n_ve_ta_multicurrency_untaxed_amount = sum_taxable + sum_exempt

    @api.depends('company_id', 'currency_id', 'move_type')
    def _compute_tax_totals(self):
        """
        EN: Override native totals to disable company currency conversion display.
        ES: Invalida los totales nativos para desactivar la visualización de la conversión a moneda de compañía.
        """
        super()._compute_tax_totals()
        for move in self:
            if move.tax_totals and isinstance(move.tax_totals, dict):
                # 1. Desactivar conversión nativa
                move.tax_totals['display_in_company_currency'] = False

                # 2. Calcular total excluyendo retenciones ISLR para evitar que el Total se muestre reducido por el ISLR
                subtotals = move.tax_totals.get('subtotals', [])
                if subtotals:
                    total_curr = 0.0
                    total_comp = 0.0
                    for subtotal_item in subtotals:
                        tax_groups = subtotal_item.get('tax_groups', [])
                        
                        # Sumar los impuestos excluyendo ISLR
                        tax_sum_curr = sum(
                            g.get('tax_amount_currency', 0.0) or 0.0 
                            for g in tax_groups 
                            if 'islr' not in (g.get('group_name', '') or '').lower()
                        )
                        tax_sum_comp = sum(
                            g.get('tax_amount', 0.0) or 0.0 
                            for g in tax_groups 
                            if 'islr' not in (g.get('group_name', '') or '').lower()
                        )
                        
                        base_curr = subtotal_item.get('base_amount_currency', 0.0) or 0.0
                        base_comp = subtotal_item.get('base_amount', 0.0) or 0.0
                        
                        total_curr += base_curr + tax_sum_curr
                        total_comp += base_comp + tax_sum_comp
                    
                    move.tax_totals['total_amount_currency'] = total_curr
                    move.tax_totals['total_amount'] = total_comp
                else:
                    move.tax_totals['total_amount_currency'] = move.tax_totals.get('total_amount_currency', 0.0)
                    move.tax_totals['total_amount'] = move.tax_totals.get('total_amount_currency', 0.0)

                move.tax_totals['base_amount'] = move.tax_totals.get('base_amount_currency', 0.0)

                # Forzar re-asignación
                move.tax_totals = move.tax_totals

    @staticmethod
    def _get_l10n_ve_ta_multicurrency_rate(move, fiscal_currency):
        """
        EN: Get the base USD -> Bs rate (manual or historical BCV).
        ES: Obtiene la tasa base USD -> Bs (manual o histórica del BCV).
        """
        company_currency = move.company_id.currency_id
        if move.l10n_ve_ta_multicurrency_use_manual_rate and move.l10n_ve_ta_multicurrency_rate:
            return move.l10n_ve_ta_multicurrency_rate
        date = move.invoice_date or move.date or fields.Date.context_today(move)
        return move.env['res.currency']._get_conversion_rate(
            company_currency, fiscal_currency, move.company_id, date
        )

    l10n_ve_ta_multicurrency_prev_currency_id = fields.Many2one('res.currency', string="Prev Currency")
    l10n_ve_ta_multicurrency_prev_manual_rate = fields.Float(string="Prev Rate", digits=(16, 4))

    @api.onchange('currency_id', 'l10n_ve_ta_multicurrency_use_manual_rate', 'l10n_ve_ta_multicurrency_rate')
    def _onchange_l10n_ve_ta_multicurrency_translate_prices(self):
        """
        EN: Convert existing line prices when switching currency to ensure consistent pricing.
        ES: Convierte los precios de las líneas existentes al cambiar de moneda para mantener consistencia.
        """
        prev_currency = self.l10n_ve_ta_multicurrency_prev_currency_id
        new_currency = self.currency_id
        if prev_currency and new_currency and prev_currency != new_currency:
            rate_date = self.invoice_date or self.date or fields.Date.context_today(self)
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
                for line in self.invoice_line_ids:
                    if line.price_unit:
                        line.price_unit = line.price_unit * rate

        self.l10n_ve_ta_multicurrency_prev_currency_id = self.currency_id
        self.l10n_ve_ta_multicurrency_prev_manual_rate = (
            self.l10n_ve_ta_multicurrency_rate
            if self.l10n_ve_ta_multicurrency_use_manual_rate
            else 0.0
        )

        # Recalcular retención ISLR para reflejar la conversión de moneda y tasas
        if hasattr(self, 'action_calculate_islr_retention') and self.state == 'draft':
            try:
                # Si ya existen datos de referencia ISLR válidos calculados por el API,
                # no debemos re-llamar al API porque el redondeo en moneda extranjera y el cambio
                # de tasa destruirían el monto exacto en Bolívares. Simplemente re-escalamos
                # los montos nativos basados en los campos de referencia (fuente de verdad).
                has_ref_data = any(line.l10n_ve_islr_amount_line_ref for line in self.invoice_line_ids)
                if has_ref_data:
                    _logger.warning("[MC] Evitando llamada al API de ISLR al cambiar moneda porque ya existen datos de referencia.")
                    is_mc_active = bool(self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic())
                    rate = self._get_islr_bs_rate() if is_mc_active else 1.0
                    for line in self.invoice_line_ids:
                        if line.l10n_ve_islr_fiscal_code:
                            if is_mc_active and rate > 0:
                                if rate > 1.0:
                                    line.l10n_ve_islr_amount_line = round((line.l10n_ve_islr_amount_line_ref or 0.0) / rate, 2)
                                    line.l10n_ve_islr_subject_amount = round((line.l10n_ve_islr_subject_amount_ref or 0.0) / rate, 2)
                                    line.l10n_ve_islr_base_retention_amount = round((line.l10n_ve_islr_base_retention_amount_ref or 0.0) / rate, 2)
                                    line.l10n_ve_islr_subtrahend = round((line.l10n_ve_islr_subtrahend_ref or 0.0) / rate, 2)
                                else:
                                    line.l10n_ve_islr_amount_line = line.l10n_ve_islr_amount_line_ref or 0.0
                                    line.l10n_ve_islr_subject_amount = line.l10n_ve_islr_subject_amount_ref or 0.0
                                    line.l10n_ve_islr_base_retention_amount = line.l10n_ve_islr_base_retention_amount_ref or 0.0
                                    line.l10n_ve_islr_subtrahend = line.l10n_ve_islr_subtrahend_ref or 0.0
                    self.l10n_ve_islr_amount = sum(self.invoice_line_ids.mapped('l10n_ve_islr_amount_line'))
                    if hasattr(self, '_inject_islr_integrated_line'):
                        self._inject_islr_integrated_line()
                else:
                    self.action_calculate_islr_retention(raise_error=False)
            except Exception as e:
                _logger.warning(
                    f"[MC] Error recalculando ISLR en onchange de moneda/tasa: {str(e)}"
                )

    def _get_islr_bs_rate(self):
        """
        Devuelve la tasa para convertir el monto del documento a Bolívares para la API ISLR.
        La API ISLR siempre espera montos en Bs.
        - Si raw_rate (doc→fiscal) >= 1: doc es moneda fuerte (USD), multiplicar para obtener Bs.
        - Si raw_rate < 1: doc YA es Bs, no convertir (retorna 1.0).
        """
        self.ensure_one()
        doc_currency = self.currency_id
        ref_currency = self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
        if not doc_currency or not ref_currency or doc_currency == ref_currency:
            return 1.0
        rate_date = self.invoice_date or self.date or fields.Date.context_today(self)
        try:
            raw_rate = doc_currency._get_conversion_rate(
                doc_currency, ref_currency, self.company_id, rate_date
            )
        except Exception:
            raw_rate = 1.0
        if not raw_rate or raw_rate <= 0:
            return 1.0
        # raw_rate >= 1: doc es moneda fuerte (ej USD→VES=544), multiplicar
        # raw_rate < 1: doc es Bs (ej VES→USD=0.0018), ya está en Bs, no convertir
        if raw_rate >= 1.0:
            # Usar tasa manual si está activa
            if self.l10n_ve_ta_multicurrency_use_manual_rate and self.l10n_ve_ta_multicurrency_rate > 0:
                return self.l10n_ve_ta_multicurrency_rate
            return raw_rate
        return 1.0

    def _get_islr_line_calculation_amount(self, line):
        _logger.warning(f"[MC-ISLR-CALC] currency={self.currency_id.name} company_currency={self.company_id.currency_id.name} fiscal_id={self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic().name if self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic() else 'None'}")
        is_mc_active = bool(self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic())
        if is_mc_active:
            rate = self._get_islr_bs_rate()
            _logger.warning(f"[MC-ISLR-CALC] bs_rate={rate} price_subtotal={line.price_subtotal} result={line.price_subtotal * rate}")
            if rate and rate > 0:
                return line.price_subtotal * rate
        _logger.warning(f"[MC-ISLR-CALC] Fallback to super() or price_subtotal={line.price_subtotal}")
        if hasattr(super(), '_get_islr_line_calculation_amount'):
            return super()._get_islr_line_calculation_amount(line)
        return line.price_subtotal

    def _process_islr_line_calculated_amounts(self, line, res_item):
        is_mc_active = bool(self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic())
        rate = self._get_islr_bs_rate() if is_mc_active else 1.0
        _logger.warning(f"[MC-ISLR-PROCESS] res_item completo del API: {res_item} | rate={rate} | is_mc_active={is_mc_active}")

        if is_mc_active and rate > 0:
            converted = res_item.copy()
            if rate > 1.0:
                # Doc currency is foreign (e.g. USD): the API returns Bs values, divide to get doc-currency amounts.
                converted['retentionAmount'] = round(res_item.get('retentionAmount', 0.0) / rate, 2)
                converted['subjectAmount'] = round(res_item.get('subjectAmount', 0.0) / rate, 2)
                converted['baseRetentionAmount'] = round(res_item.get('baseRetentionAmount', 0.0) / rate, 2)
                converted['subtrahend'] = round(res_item.get('subtrahend', 0.0) / rate, 2)
            # rate == 1.0: doc is already VES/VEF, API values are already in doc currency — no conversion needed.

            # 1. Guardar en la moneda del documento (módulo base)
            if hasattr(super(), '_process_islr_line_calculated_amounts'):
                super()._process_islr_line_calculated_amounts(line, converted)

            # 2. Guardar el valor puro del API (Bs) en los campos _ref DESPUÉS del super()
            #    para que no sean sobreescritos por ningún módulo base.
            ret_bs = res_item.get('retentionAmount', 0.0)
            sub_bs = res_item.get('subjectAmount', 0.0)
            base_ret_bs = res_item.get('baseRetentionAmount', 0.0)
            subt_bs = res_item.get('subtrahend', 0.0)
            ret_pct = res_item.get('retentionPercentage', 0.0)

            if not base_ret_bs and ret_bs and ret_pct:
                base_ret_bs = round(ret_bs / (ret_pct / 100.0), 2)
            if not sub_bs and base_ret_bs:
                sub_bs = round(base_ret_bs + subt_bs, 2)

            if hasattr(line, 'l10n_ve_islr_amount_line_ref'):
                line.l10n_ve_islr_amount_line_ref = ret_bs
            if hasattr(line, 'l10n_ve_islr_subject_amount_ref'):
                line.l10n_ve_islr_subject_amount_ref = sub_bs
            if hasattr(line, 'l10n_ve_islr_base_retention_amount_ref'):
                line.l10n_ve_islr_base_retention_amount_ref = base_ret_bs
            if hasattr(line, 'l10n_ve_islr_subtrahend_ref'):
                line.l10n_ve_islr_subtrahend_ref = subt_bs

        elif hasattr(super(), '_process_islr_line_calculated_amounts'):
            super()._process_islr_line_calculated_amounts(line, res_item)

    def _inject_islr_integrated_line(self):
        """
        Multicurrency override for _inject_islr_integrated_line.
        Ensures that debit/credit are in company currency (Bs.F) and
        amount_currency is set to the document currency (USD).
        """
        self.ensure_one()
        if self.state != 'draft':
            return

        # Si el módulo fiscal de base no está instalado, salimos
        if not hasattr(super(), '_inject_islr_integrated_line'):
            return

        company_currency = self.company_id.currency_id
        doc_currency = self.currency_id

        # Si no hay multimoneda activa, usar el comportamiento nativo
        if not self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic() or doc_currency == company_currency:
            res = super()._inject_islr_integrated_line()
            config_obj = self.env['simplitfiscal.config'].search([
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if config_obj and config_obj.l10n_ve_islr_account_id:
                existing_islr_lines = self.line_ids.filtered(
                    lambda l: l.account_id == config_obj.l10n_ve_islr_account_id and l.display_type == 'tax'
                )
                is_purchase = self.move_type in ('in_invoice', 'in_refund')
                if is_purchase:
                    counterpart_line = self.line_ids.filtered(lambda l: l.account_type == 'liability_payable')
                else:
                    counterpart_line = self.line_ids.filtered(lambda l: l.account_type == 'asset_receivable')
                
                for line in (existing_islr_lines | counterpart_line):
                    line.with_context(check_move_validity=False).write({
                        'amount_currency': line.debit - line.credit
                    })
            return res

        config = self.env['simplitfiscal.config'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not config or not config.l10n_ve_islr_account_id:
            raise ValidationError(_("Debe configurar la Cuenta de ISLR en la configuración fiscal para el asiento integrado."))

        is_purchase = self.move_type in ('in_invoice', 'in_refund')
        is_sale = self.move_type in ('out_invoice', 'out_refund')
        
        if not is_purchase and not is_sale:
            return

        # Identificar líneas existentes y línea de contrapartida (Payable o Receivable)
        existing_islr_lines = self.line_ids.filtered(
            lambda l: l.account_id == config.l10n_ve_islr_account_id and l.display_type == 'tax'
        )
        
        if is_purchase:
            counterpart_line = self.line_ids.filtered(lambda l: l.account_type == 'liability_payable')
        else:
            counterpart_line = self.line_ids.filtered(lambda l: l.account_type == 'asset_receivable')

        if not counterpart_line:
            _logger.warning(f"[MC-ISLR] No se encontró línea de contrapartida (Payable/Receivable) para {self.name}")
            return

        counter_l = counterpart_line[0]

        # 1. Determinar el monto en Bolívares (VES)
        # l10n_ve_islr_amount o la sumatoria de las líneas de referencia siempre están en VES
        if self._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic():
            islr_bs = sum(getattr(l, 'l10n_ve_islr_amount_line_ref', 0.0) or 0.0 for l in self.invoice_line_ids)
        else:
            islr_bs = self.l10n_ve_islr_amount
        
        # 2. Convertir a moneda de la compañía y moneda del documento según corresponda
        if company_currency.name in {'VES', 'VEF', 'VEB'}:
            islr_company = islr_bs
        else:
            # La compañía está en USD/EUR, convertir de VES a la moneda de la compañía
            rate_date = self.invoice_date or self.date or fields.Date.context_today(self)
            ves_curr = self.env['res.currency'].search([('name', 'in', ('VES', 'VEF', 'VEB'))], limit=1) or company_currency
            islr_company = ves_curr._convert(islr_bs, company_currency, self.company_id, rate_date)
            
        if doc_currency.name in {'VES', 'VEF', 'VEB'}:
            islr_doc = islr_bs
        else:
            # El documento está en USD/EUR, convertir de VES a la moneda del documento
            rate_date = self.invoice_date or self.date or fields.Date.context_today(self)
            ves_curr = self.env['res.currency'].search([('name', 'in', ('VES', 'VEF', 'VEB'))], limit=1) or doc_currency
            islr_doc = ves_curr._convert(islr_bs, doc_currency, self.company_id, rate_date)

        # Lógica de Actualización / Inserción respetando multimoneda
        if existing_islr_lines:
            line_to_update = existing_islr_lines[0]

            # Para USD invoices: el amount_currency del Payable/Receivable debe ser:
            # -(total_en_moneda_doc - islr_doc) para créditos, +(total - islr_doc) para débitos
            # Calculamos el total de la factura en moneda del documento:
            total_doc = self.amount_total  # en moneda del documento (USD si doc_currency=USD)
            # El Payable tenía: credit_bs = total_bs_sin_islr + old_islr_bs
            # Después de inyectar ISLR por separado, Payable debe ser: total_bs - islr_bs

            if self.move_type == 'in_invoice':  # Compra: Payable es crédito (AC < 0)
                delta_company = line_to_update.credit - islr_company
                new_counter_credit = max(0.0, counter_l.credit + delta_company)
                # AC del payable = -(total_doc - islr_doc), siempre negativo
                new_counter_ac = min(-(total_doc - islr_doc), 0.0) if total_doc else min(counter_l.amount_currency + islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'credit': new_counter_credit,
                    'amount_currency': new_counter_ac,
                })
                line_to_update.with_context(check_move_validity=False).write({
                    'credit': islr_company,
                    'debit': 0.0,
                    'amount_currency': -abs(islr_doc),
                    'currency_id': doc_currency.id,
                })

            elif self.move_type == 'in_refund':  # NC Compra: Payable es débito (AC > 0)
                delta_company = line_to_update.debit - islr_company
                new_counter_debit = max(0.0, counter_l.debit + delta_company)
                new_counter_ac = max(total_doc - islr_doc, 0.0) if total_doc else max(counter_l.amount_currency - islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'debit': new_counter_debit,
                    'amount_currency': new_counter_ac,
                })
                line_to_update.with_context(check_move_validity=False).write({
                    'debit': islr_company,
                    'credit': 0.0,
                    'amount_currency': abs(islr_doc),
                    'currency_id': doc_currency.id,
                })

            elif self.move_type == 'out_invoice':  # Venta: Receivable es débito (AC > 0)
                delta_company = line_to_update.debit - islr_company
                new_counter_debit = max(0.0, counter_l.debit + delta_company)
                new_counter_ac = max(total_doc - islr_doc, 0.0) if total_doc else max(counter_l.amount_currency - islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'debit': new_counter_debit,
                    'amount_currency': new_counter_ac,
                })
                line_to_update.with_context(check_move_validity=False).write({
                    'debit': islr_company,
                    'credit': 0.0,
                    'amount_currency': abs(islr_doc),
                    'currency_id': doc_currency.id,
                })

            elif self.move_type == 'out_refund':  # NC Venta: Receivable es crédito (AC < 0)
                delta_company = line_to_update.credit - islr_company
                new_counter_credit = max(0.0, counter_l.credit + delta_company)
                new_counter_ac = min(-(total_doc - islr_doc), 0.0) if total_doc else min(counter_l.amount_currency + islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'credit': new_counter_credit,
                    'amount_currency': new_counter_ac,
                })
                line_to_update.with_context(check_move_validity=False).write({
                    'credit': islr_company,
                    'debit': 0.0,
                    'amount_currency': -abs(islr_doc),
                    'currency_id': doc_currency.id,
                })

            for extra_line in existing_islr_lines[1:]:
                extra_line.with_context(check_move_validity=False).write({
                    'debit': 0.0,
                    'credit': 0.0,
                    'amount_currency': 0.0,
                })

        elif islr_company > 0:
            if self.move_type == 'in_invoice':
                # Compra: Payable es crédito (amount_currency < 0)
                new_counter_ac = min(-(self.amount_total - islr_doc), 0.0) if self.amount_total else min(counter_l.amount_currency + islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'credit': max(0.0, counter_l.credit - islr_company),
                    'amount_currency': new_counter_ac,
                })
                vals = {
                    'debit': 0.0,
                    'credit': islr_company,
                    'amount_currency': -abs(islr_doc),
                    'currency_id': doc_currency.id,
                    'name': f"Retención ISLR {self.name or ''}"
                }
            elif self.move_type == 'in_refund':
                # NC Compra: Payable es débito (amount_currency > 0)
                new_counter_ac = max(self.amount_total - islr_doc, 0.0) if self.amount_total else max(counter_l.amount_currency - islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'debit': max(0.0, counter_l.debit - islr_company),
                    'amount_currency': new_counter_ac,
                })
                vals = {
                    'debit': islr_company,
                    'credit': 0.0,
                    'amount_currency': abs(islr_doc),
                    'currency_id': doc_currency.id,
                    'name': f"Reverso Retención ISLR {self.name or ''}"
                }
            elif self.move_type == 'out_invoice':
                # Venta: Receivable es débito (amount_currency > 0)
                new_counter_ac = max(self.amount_total - islr_doc, 0.0) if self.amount_total else max(counter_l.amount_currency - islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'debit': max(0.0, counter_l.debit - islr_company),
                    'amount_currency': new_counter_ac,
                })
                vals = {
                    'debit': islr_company,
                    'credit': 0.0,
                    'amount_currency': abs(islr_doc),
                    'currency_id': doc_currency.id,
                    'name': f"Retención ISLR {self.name or ''}"
                }
            elif self.move_type == 'out_refund':
                # NC Venta: Receivable es crédito (amount_currency < 0)
                new_counter_ac = min(-(self.amount_total - islr_doc), 0.0) if self.amount_total else min(counter_l.amount_currency + islr_doc, 0.0)
                counter_l.with_context(check_move_validity=False).write({
                    'credit': max(0.0, counter_l.credit - islr_company),
                    'amount_currency': new_counter_ac,
                })
                vals = {
                    'debit': 0.0,
                    'credit': islr_company,
                    'amount_currency': -abs(islr_doc),
                    'currency_id': doc_currency.id,
                    'name': f"Reverso Retención ISLR {self.name or ''}"
                }
            
            self.with_context(check_move_validity=False).write({
                'line_ids': [(0, 0, {
                    **vals,
                    'partner_id': self.partner_id.id,
                    'account_id': config.l10n_ve_islr_account_id.id,
                    'date_maturity': self.invoice_date_due or self.invoice_date or fields.Date.context_today(self),
                    'display_type': 'tax', 
                })]
            })

        # Red de seguridad definitiva para amount_currency para evitar cualquier error de validación SQL
        for line in self.line_ids:
            if not line.currency_id or line.currency_id == company_currency:
                if line.amount_currency != (line.debit - line.credit):
                    line.with_context(check_move_validity=False).write({
                        'amount_currency': line.debit - line.credit
                    })
            else:
                balance = line.debit - line.credit
                if balance < 0 and line.amount_currency > 0:
                    line.with_context(check_move_validity=False).write({
                        'amount_currency': -abs(line.amount_currency)
                    })
                elif balance > 0 and line.amount_currency < 0:
                    line.with_context(check_move_validity=False).write({
                        'amount_currency': abs(line.amount_currency)
                    })
                elif balance == 0 and line.amount_currency != 0:
                    line.with_context(check_move_validity=False).write({
                        'amount_currency': 0.0
                    })

        _logger.info(f"[MC-ISLR] Inyectada/Actualizada línea de retención integrada multimoneda en move {self.id}")

    def _post(self, soft=True):
        # Asegurar red de seguridad en confirmación para evitar cualquier error de validación
        for move in self:
            company_currency = move.company_id.currency_id
            for line in move.line_ids:
                if not line.currency_id or line.currency_id == company_currency:
                    if line.amount_currency != (line.debit - line.credit):
                        line.with_context(check_move_validity=False).write({
                            'amount_currency': line.debit - line.credit
                        })
                else:
                    balance = line.debit - line.credit
                    if balance < 0 and line.amount_currency > 0:
                        line.with_context(check_move_validity=False).write({
                            'amount_currency': -abs(line.amount_currency)
                        })
                    elif balance > 0 and line.amount_currency < 0:
                        line.with_context(check_move_validity=False).write({
                            'amount_currency': abs(line.amount_currency)
                        })
                    elif balance == 0 and line.amount_currency != 0:
                        line.with_context(check_move_validity=False).write({
                            'amount_currency': 0.0
                        })
        return super()._post(soft=soft)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _get_l10n_ve_ta_multicurrency_fiscal_id_dynamic(self):
        self.ensure_one()
        if self.move_id:
            return self.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
        return self.company_id.currency_id

    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        string='Fiscal Equivalent Currency',
        related='move_id.l10n_ve_ta_multicurrency_fiscal_id',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'debit' in vals or 'credit' in vals:
                debit = vals.get('debit', 0.0) or 0.0
                credit = vals.get('credit', 0.0) or 0.0
                balance = debit - credit
                move_id = vals.get('move_id')
                if move_id:
                    move = self.env['account.move'].browse(move_id)
                    comp_curr = move.company_id.currency_id
                    curr_id = vals.get('currency_id') or comp_curr.id
                    if curr_id == comp_curr.id:
                        vals['amount_currency'] = balance
                    else:
                        amc = vals.get('amount_currency', 0.0) or 0.0
                        if balance < 0 and amc > 0:
                            vals['amount_currency'] = -abs(amc)
                        elif balance > 0 and amc < 0:
                            vals['amount_currency'] = abs(amc)
                        elif balance == 0:
                            vals['amount_currency'] = 0.0
        return super().create(vals_list)

    def write(self, vals):
        if 'amount_currency' in vals and len(vals) == 1:
            return super().write(vals)
            
        res = super().write(vals)
        
        # Corregir después de escribir para asegurar cumplimiento de restricciones de base de datos
        for line in self:
            comp_curr = line.company_id.currency_id
            balance = line.debit - line.credit
            if line.currency_id == comp_curr:
                if line.amount_currency != balance:
                    super(AccountMoveLine, line.with_context(check_move_validity=False)).write({
                        'amount_currency': balance
                    })
            else:
                amc = line.amount_currency
                if balance < 0 and amc > 0:
                    super(AccountMoveLine, line.with_context(check_move_validity=False)).write({
                        'amount_currency': -abs(amc)
                    })
                elif balance > 0 and amc < 0:
                    super(AccountMoveLine, line.with_context(check_move_validity=False)).write({
                        'amount_currency': abs(amc)
                    })
                elif balance == 0 and amc != 0:
                    super(AccountMoveLine, line.with_context(check_move_validity=False)).write({
                        'amount_currency': 0.0
                    })
        return res

    @api.onchange('product_id')
    def _onchange_product_id_l10n_ve_ta_multicurrency_hook(self):
        """
        EN: Onchange on product_id to apply our custom bimonetary rate to the price.
            NOTE: account.move.line in Odoo 18 does not define _onchange_product_id,
            so we register our own separate onchange instead of calling super().
        ES: Onchange en product_id para aplicar nuestra tasa bimonetaria personalizada al precio.
            NOTA: account.move.line en Odoo 18 no define _onchange_product_id,
            por lo que registramos nuestro propio onchange separado en lugar de llamar a super().
        """
        self._onchange_product_id_l10n_ve_ta_multicurrency()

    def _onchange_product_id_l10n_ve_ta_multicurrency(self):
        """
        EN: Adjust price_unit proportionally ONLY when a manual rate is active.
            Let Odoo's native pricelist/conversion handle the price normally otherwise.
        ES: Ajusta price_unit proporcionalmente SOLO cuando una tasa manual está activa.
            De lo contrario, deja que el pricelist/conversión nativo de Odoo maneje el precio.
        """
        if not self.product_id or not self.move_id:
            return

        # Solo ajustar si se usa tasa manual activa y válida
        if self.move_id.l10n_ve_ta_multicurrency_use_manual_rate and self.move_id.l10n_ve_ta_multicurrency_rate > 0:
            company_currency = self.move_id.company_id.currency_id
            if company_currency and self.move_id.currency_id != company_currency:
                rate_date = self.move_id.invoice_date or self.move_id.date or fields.Date.context_today(self)
                try:
                    conv_rate = company_currency._get_conversion_rate(
                        company_currency, self.move_id.currency_id, self.move_id.company_id, rate_date
                    )
                except Exception:
                    conv_rate = 1.0
                if conv_rate:
                    # conv_rate es VES -> USD (tasa histórica). manual_rate es VES/USD.
                    # El factor para ajustar el USD nativo a USD manual es: (1 / manual_rate) / conv_rate
                    manual_factor = (1.0 / self.move_id.l10n_ve_ta_multicurrency_rate) / conv_rate
                    self.price_unit = self.price_unit * manual_factor

    # ---- Per-line fiscal fields (Section D of MD) ----
    l10n_ve_ta_multicurrency_price_unit = fields.Float(
        string='Unit Price Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_taxable_amount = fields.Float(
        string='Taxable Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_exempt_amount = fields.Float(
        string='Exempt Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_discount_amount = fields.Float(
        string='Discount Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_tax_amount = fields.Float(
        string='Tax Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_total_amount = fields.Float(
        string='Total Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )

    # ---- Per-line fields in DOCUMENT CURRENCY (Requested by user) ----
    l10n_ve_ta_multicurrency_move_currency_id = fields.Many2one(
        'res.currency',
        string='Move Currency',
        related='move_id.currency_id',
        store=False,
    )
    l10n_ve_ta_multicurrency_taxable_amount_curr = fields.Monetary(
        string='Gravable',
        currency_field='l10n_ve_ta_multicurrency_move_currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_exempt_amount_curr = fields.Monetary(
        string='Exento',
        currency_field='l10n_ve_ta_multicurrency_move_currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )
    l10n_ve_ta_multicurrency_tax_amount_curr = fields.Monetary(
        string='Impuesto',
        currency_field='l10n_ve_ta_multicurrency_move_currency_id',
        compute='_compute_l10n_ve_ta_multicurrency_amounts',
    )

    l10n_ve_ta_multicurrency_journal_doc_currency_id = fields.Many2one(
        'res.currency',
        string='Journal Doc Currency',
        compute='_compute_l10n_ve_ta_multicurrency_journal_currencies',
    )
    l10n_ve_ta_multicurrency_journal_ref_currency_id = fields.Many2one(
        'res.currency',
        string='Journal Ref Currency',
        compute='_compute_l10n_ve_ta_multicurrency_journal_currencies',
    )

    # Accounting entry amounts (Section F - only on account.move.line)
    l10n_ve_ta_multicurrency_debit_doc_amount = fields.Float(
        string='Débito Doc',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_debit_credit_fiscal',
    )
    l10n_ve_ta_multicurrency_credit_doc_amount = fields.Float(
        string='Crédito Doc',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_debit_credit_fiscal',
    )
    l10n_ve_ta_multicurrency_debit_amount = fields.Float(
        string='Debit Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_debit_credit_fiscal',
        store=True,
    )
    l10n_ve_ta_multicurrency_credit_amount = fields.Float(
        string='Credit Ref.',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_debit_credit_fiscal',
        store=True,
    )

    @api.depends('move_id.currency_id', 'company_id.currency_id')
    def _compute_l10n_ve_ta_multicurrency_journal_currencies(self):
        for line in self:
            move = line.move_id
            company_currency = line.company_id.currency_id
            
            # La moneda del documento es la moneda de la factura (move.currency_id), o la de la compañía
            doc_currency = move.currency_id or company_currency
            line.l10n_ve_ta_multicurrency_journal_doc_currency_id = doc_currency.id
            
            # Buscar la moneda extranjera activa
            foreign_curr = self.env['res.currency'].sudo().search([
                ('id', '!=', company_currency.id),
                ('active', '=', True)
            ], order='name asc', limit=1)
            
            # La moneda de referencia es la opuesta (espejo)
            if doc_currency == company_currency:
                line.l10n_ve_ta_multicurrency_journal_ref_currency_id = foreign_curr.id if foreign_curr else company_currency.id
            else:
                line.l10n_ve_ta_multicurrency_journal_ref_currency_id = company_currency.id

    @api.depends('debit', 'credit', 'amount_currency', 'currency_id', 'move_id.currency_id', 'move_id.l10n_ve_ta_multicurrency_applied_rate',
                 'l10n_ve_ta_multicurrency_journal_doc_currency_id', 'l10n_ve_ta_multicurrency_journal_ref_currency_id')
    def _compute_l10n_ve_ta_multicurrency_debit_credit_fiscal(self):
        """
        Calcula débitos y créditos tanto en moneda de documento como en moneda de referencia (inversa/espejo).
        """
        for line in self:
            move = line.move_id
            company_currency = line.company_id.currency_id
            doc_currency = line.l10n_ve_ta_multicurrency_journal_doc_currency_id or move.currency_id or company_currency
            ref_currency = line.l10n_ve_ta_multicurrency_journal_ref_currency_id
            
            rate_date = move.invoice_date or move.date or fields.Date.context_today(line)
            
            # 1. Calcular en Moneda del Documento (Doc Amount)
            if doc_currency == company_currency:
                line.l10n_ve_ta_multicurrency_debit_doc_amount = line.debit
                line.l10n_ve_ta_multicurrency_credit_doc_amount = line.credit
            else:
                try:
                    factor = company_currency._get_conversion_rate(
                        company_currency, doc_currency, line.company_id, rate_date
                    )
                except Exception:
                    factor = 1.0
                line.l10n_ve_ta_multicurrency_debit_doc_amount = line.debit * (factor or 1.0)
                line.l10n_ve_ta_multicurrency_credit_doc_amount = line.credit * (factor or 1.0)
                
            # 2. Calcular en Moneda de Referencia (Ref Amount)
            if ref_currency == company_currency:
                line.l10n_ve_ta_multicurrency_debit_amount = line.debit
                line.l10n_ve_ta_multicurrency_credit_amount = line.credit
            else:
                try:
                    factor = company_currency._get_conversion_rate(
                        company_currency, ref_currency, line.company_id, rate_date
                    )
                except Exception:
                    factor = 1.0
                line.l10n_ve_ta_multicurrency_debit_amount = line.debit * (factor or 1.0)
                line.l10n_ve_ta_multicurrency_credit_amount = line.credit * (factor or 1.0)

    l10n_ve_ta_multicurrency_price_subtotal_alt = fields.Float(
        string='Subtotal (Co.)',
        digits=(16, 4),
        compute='_compute_l10n_ve_ta_multicurrency_price_subtotal_alt',
    )

    # ----------------------------------------------------------------
    # Compute: amounts per line in the equivalent currency
    # ----------------------------------------------------------------
    @api.depends(
        'price_subtotal',
        'price_total',
        'discount',
        'quantity',
        'price_unit',
        'tax_ids',
        'display_type',
        'move_id.currency_id',
        'move_id.l10n_ve_ta_multicurrency_rate', # Keep to trigger update
        'move_id.l10n_ve_ta_multicurrency_use_manual_rate',
        'move_id.l10n_ve_ta_multicurrency_applied_rate',
    )
    def _compute_l10n_ve_ta_multicurrency_amounts(self):
        """
        EN: Compute fiscal amounts per line in the same currency as the document.
        ES: Calcula los montos fiscales por línea en la misma moneda que el documento.
        """
        for line in self:
            if line.display_type in ('line_section', 'line_note'):
                line.l10n_ve_ta_multicurrency_price_unit = 0.0
                line.l10n_ve_ta_multicurrency_taxable_amount = 0.0
                line.l10n_ve_ta_multicurrency_exempt_amount = 0.0
                line.l10n_ve_ta_multicurrency_discount_amount = 0.0
                line.l10n_ve_ta_multicurrency_tax_amount = 0.0
                line.l10n_ve_ta_multicurrency_total_amount = 0.0
                continue

            # Use the refined factor calculation helper
            factor = line.move_id._get_l10n_ve_ta_multicurrency_factor()
                
            is_exempt = not bool(line.tax_ids)
            subtotal = (line.price_subtotal or 0.0) * factor
            total = (line.price_total or 0.0) * factor
            unit_price = (line.price_unit or 0.0) * factor

            line.l10n_ve_ta_multicurrency_price_unit = unit_price
            line.l10n_ve_ta_multicurrency_taxable_amount = subtotal if not is_exempt else 0.0
            line.l10n_ve_ta_multicurrency_exempt_amount = subtotal if is_exempt else 0.0
            
            # Nominal price before discount
            nominal = (line.quantity or 0.0) * unit_price
            line.l10n_ve_ta_multicurrency_discount_amount = max(nominal - subtotal, 0.0)
            
            # FISCAL FIX: En Odoo 18, price_tax incluye retenciones si están en el mismo grupo.
            # Para el reporte fiscal necesitamos el IVA BRUTO (solo positivos).
            tax_results = line.tax_ids.compute_all(line.price_unit, line.move_id.currency_id, line.quantity, product=line.product_id, partner=line.move_id.partner_id)
            # Solo sumamos los impuestos positivos (IVA) y los convertimos a la moneda fiscal usando el factor
            iva_bruto_currency = sum(t['amount'] for t in tax_results['taxes'] if t['amount'] > 0)
            
            line.l10n_ve_ta_multicurrency_tax_amount = iva_bruto_currency * factor
            line.l10n_ve_ta_multicurrency_total_amount = subtotal + (iva_bruto_currency * factor)

            # Document currency fields (Without factor)
            line.l10n_ve_ta_multicurrency_taxable_amount_curr = line.price_subtotal if not is_exempt else 0.0
            line.l10n_ve_ta_multicurrency_exempt_amount_curr = line.price_subtotal if is_exempt else 0.0
            line.l10n_ve_ta_multicurrency_tax_amount_curr = iva_bruto_currency

    # ----------------------------------------------------------------
    # Compute: Subtotal in company currency
    # ----------------------------------------------------------------
    # ----------------------------------------------------------------
    # Compute: Subtotal in company currency
    # ----------------------------------------------------------------
    @api.depends('price_subtotal', 'currency_id', 'company_id')
    def _compute_l10n_ve_ta_multicurrency_price_subtotal_alt(self):
        """
        EN: Compute the line subtotal in the company's base currency.
        ES: Calcula el subtotal de la línea en la moneda base de la compañía.
        """
        for line in self:
            if (
                line.currency_id
                and line.company_currency_id
                and line.currency_id != line.company_currency_id
            ):
                date = (
                    line.move_id.invoice_date
                    or line.move_id.date
                    or fields.Date.context_today(line)
                )
                line.l10n_ve_ta_multicurrency_price_subtotal_alt = line.currency_id._convert(
                    line.price_subtotal,
                    line.company_currency_id,
                    line.company_id,
                    date,
                )
            else:
                line.l10n_ve_ta_multicurrency_price_subtotal_alt = line.price_subtotal

    # ---- CAMPOS DE REFERENCIA ISLR MONETARIA ----
    # Placeholders para campos definidos por l10n_ve_simplit_fiscal (evitan error si no está instalado)
    l10n_ve_islr_amount_line = fields.Monetary(string='Retención ISLR Línea')
    l10n_ve_islr_subject_amount = fields.Monetary(string='Monto Sujeto ISLR')
    l10n_ve_islr_subject_percentage = fields.Float(string='% Base Sujeta ISLR')
    l10n_ve_islr_retention_percentage = fields.Float(string='% Retención ISLR')
    l10n_ve_islr_subtrahend = fields.Monetary(string='Sustraendo ISLR')
    l10n_ve_islr_base_retention_amount = fields.Monetary(string='Cálculo Base Retención ISLR')
    l10n_ve_islr_fiscal_code = fields.Char(string='Código Fiscal ISLR')
    l10n_ve_islr_subject_amount_display = fields.Char(string='Monto Sujeto ISLR')
    l10n_ve_islr_retention_calculation_display = fields.Char(string='Calc. Imp Ret')

    l10n_ve_islr_amount_line_ref = fields.Float(string='Monto Retenido ISLR (Ref.)', digits=(16, 2), store=True)
    l10n_ve_islr_subject_amount_ref = fields.Float(string='Monto Sujeto ISLR (Ref.)', digits=(16, 2), store=True)
    l10n_ve_islr_base_retention_amount_ref = fields.Float(string='Base Retención ISLR (Ref.)', digits=(16, 2), store=True)
    l10n_ve_islr_subtrahend_ref = fields.Float(string='Sustraendo ISLR (Ref.)', digits=(16, 2), store=True)
    l10n_ve_islr_price_subtotal_ref_display = fields.Char(string='Base Imponible Ref.', compute='_compute_l10n_ve_islr_ref_amounts')
    l10n_ve_islr_subject_amount_ref_display = fields.Char(string='Monto Sujeto Ref.', compute='_compute_l10n_ve_islr_ref_amounts')
    l10n_ve_islr_base_retention_amount_ref_display = fields.Char(string='Base Retención Ref.', compute='_compute_l10n_ve_islr_ref_amounts')
    l10n_ve_islr_retention_calculation_ref_display = fields.Char(string='Calc. Imp Ref.', compute='_compute_l10n_ve_islr_ref_amounts')
    l10n_ve_islr_subtrahend_ref_display = fields.Char(string='Sustraendo Ref.', compute='_compute_l10n_ve_islr_ref_amounts')
    l10n_ve_islr_amount_line_ref_display = fields.Char(string='Monto Retenido Ref.', compute='_compute_l10n_ve_islr_ref_amounts')

    def _format_specific_currency(self, amount, currency):
        self.ensure_one()
        val = amount or 0.0
        formatted = "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
        symbol = currency.symbol or currency.name or ''
        res = f"{formatted} {symbol}"
        _logger.warning(f"[MC-FORMAT-SPECIFIC] amount={amount} currency={currency.name} returning={res}")
        return res

    @api.depends(
        'price_subtotal',
        'l10n_ve_islr_subtrahend_ref',
        'l10n_ve_islr_amount_line_ref',
        'l10n_ve_islr_subject_amount_ref',
        'l10n_ve_islr_base_retention_amount_ref',
        'l10n_ve_islr_retention_percentage',
        'l10n_ve_islr_fiscal_code',
        'currency_id',
        'move_id.currency_id',
        'move_id.l10n_ve_ta_multicurrency_fiscal_id',
        'move_id.l10n_ve_ta_multicurrency_applied_rate',
    )
    def _compute_l10n_ve_islr_ref_amounts(self):
        for line in self:
            # ----------------------------------------------------------------
            # Detectar la moneda Bolívares (VES/VEF/VEB) sin importar si la
            # factura está en USD o en VES.
            # Lógica: el MC le dice al fiscal "usa este monto en Bs calculado
            # con la tasa". Los campos *_ref siempre contienen Bs del API.
            # ----------------------------------------------------------------
            ves_names = {'VES', 'VEF', 'VEB'}
            if line.move_id.currency_id.name in ves_names:
                bs_currency = line.move_id.currency_id
            elif (line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic() and
                  line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic().name in ves_names):
                bs_currency = line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            else:
                bs_currency = line.company_id.currency_id

            # Base imponible en Bs: price_subtotal * tasa Bs (igual que lo
            # que el MC envía al API fiscal)
            bs_rate = line.move_id._get_islr_bs_rate()
            base_imponible_bs = (line.price_subtotal or 0.0) * bs_rate
            line.l10n_ve_islr_price_subtotal_ref_display = line._format_specific_currency(base_imponible_bs, bs_currency)

            # Los campos *_ref guardan el valor PURO del API en Bs (fuente de verdad).
            # IMPORTANTE: el fallback NO debe usar `native * bs_rate`. Los campos
            # nativos pueden estar redondeados en la moneda del documento (ej. USD
            # 0.01) y multiplicarlos por la tasa reintroduce el error (0.01 × 554 = 5.54).
            # Cuando *_ref está vacío, se deriva localmente solo lo exacto y el
            # sustraendo se deja en 0 (la migración rellena el valor real del API).
            ret_pct = line.l10n_ve_islr_retention_percentage or 0.0
            subject_pct = getattr(line, 'l10n_ve_islr_subject_percentage', 0.0) or 0.0

            amount_line_ref = line.l10n_ve_islr_amount_line_ref
            amount_line_bs = amount_line_ref or 0.0

            subject_amount_ref = line.l10n_ve_islr_subject_amount_ref
            subject_amount_bs = subject_amount_ref or 0.0

            base_retention_ref = line.l10n_ve_islr_base_retention_amount_ref
            base_retention_bs = base_retention_ref or 0.0

            subtrahend_ref = line.l10n_ve_islr_subtrahend_ref
            subtrahend_bs = subtrahend_ref or 0.0

            # Derivaciones exactas a partir de la base imponible en Bs (sin API):
            #   subjectAmount      = base_imponible × subject%
            #   baseRetentionAmount = subjectAmount × retention%
            # El sustraendo NO es derivable localmente: si no hay *_ref se queda en 0
            # hasta que la migración (re-llamada al API) lo rellene.
            if not subject_amount_bs:
                if subject_pct and base_imponible_bs:
                    subject_amount_bs = round(base_imponible_bs * (subject_pct / 100.0), 2)
                else:
                    # Venezuela: caso típico 100% sujeto → subjectAmount = base_imponible
                    subject_amount_bs = base_imponible_bs
            if not base_retention_bs:
                if ret_pct and subject_amount_bs:
                    base_retention_bs = round(subject_amount_bs * (ret_pct / 100.0), 2)
                elif amount_line_bs:
                    base_retention_bs = round(amount_line_bs + subtrahend_bs, 2)
            if not amount_line_bs and base_retention_bs:
                amount_line_bs = round(base_retention_bs - subtrahend_bs, 2)

            line.l10n_ve_islr_subtrahend_ref_display = line._format_specific_currency(subtrahend_bs, bs_currency)
            line.l10n_ve_islr_amount_line_ref_display = line._format_specific_currency(amount_line_bs, bs_currency)

            line.l10n_ve_islr_subject_amount_ref_display = line._format_specific_currency(subject_amount_bs, bs_currency)
            line.l10n_ve_islr_base_retention_amount_ref_display = line._format_specific_currency(base_retention_bs, bs_currency)

            # Calc. Imp Ref. siempre en Bs
            if not line.l10n_ve_islr_fiscal_code:
                line.l10n_ve_islr_retention_calculation_ref_display = ""
            else:
                symbol = bs_currency.symbol or bs_currency.name or ''
                percentage = line.l10n_ve_islr_retention_percentage
                if not percentage and base_retention_bs and subject_amount_bs:
                    percentage = round((base_retention_bs / subject_amount_bs) * 100.0, 2)
                formatted_amount = "{:,.2f}".format(base_retention_bs).replace(",", "X").replace(".", ",").replace("X", ".")
                line.l10n_ve_islr_retention_calculation_ref_display = f"{formatted_amount} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    # Sobrescribir computados de display para inyectar la moneda de referencia dinámicamente
    @api.depends('l10n_ve_islr_subject_amount', 'l10n_ve_islr_subject_percentage', 'currency_id')
    def _compute_l10n_ve_islr_subject_amount_display(self):
        if hasattr(super(), '_compute_l10n_ve_islr_subject_amount_display'):
            super()._compute_l10n_ve_islr_subject_amount_display()
        for line in self:
            rate = line.move_id.l10n_ve_ta_multicurrency_applied_rate or 1.0
            is_mc = line.currency_id != line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            if is_mc and rate > 0:
                amount_ref = line.l10n_ve_islr_subject_amount * rate
                percentage = line.l10n_ve_islr_subject_percentage
                if not percentage and line.price_subtotal and line.l10n_ve_islr_subject_amount:
                    percentage = round((line.l10n_ve_islr_subject_amount / line.price_subtotal) * 100.0, 2)
                formatted = "{:,.2f}".format(amount_ref).replace(",", "X").replace(".", ",").replace("X", ".")
                fiscal_curr = line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
                symbol = fiscal_curr.symbol or fiscal_curr.name or ''
                line.l10n_ve_islr_subject_amount_display = f"{formatted} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    @api.depends('l10n_ve_islr_base_retention_amount', 'l10n_ve_islr_retention_percentage', 'currency_id')
    def _compute_l10n_ve_islr_retention_calculation_display(self):
        if hasattr(super(), '_compute_l10n_ve_islr_retention_calculation_display'):
            super()._compute_l10n_ve_islr_retention_calculation_display()
        for line in self:
            rate = line.move_id.l10n_ve_ta_multicurrency_applied_rate or 1.0
            is_mc = line.currency_id != line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
            if is_mc and rate > 0:
                amount_ref = line.l10n_ve_islr_base_retention_amount * rate
                percentage = line.l10n_ve_islr_retention_percentage
                if not percentage and line.l10n_ve_islr_base_retention_amount:
                    subject = line.l10n_ve_islr_subject_amount or line.price_subtotal
                    if subject:
                        percentage = round((line.l10n_ve_islr_base_retention_amount / subject) * 100.0, 2)
                formatted = "{:,.2f}".format(amount_ref).replace(",", "X").replace(".", ",").replace("X", ".")
                fiscal_curr = line.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
                symbol = fiscal_curr.symbol or fiscal_curr.name or ''
                line.l10n_ve_islr_retention_calculation_display = f"{formatted} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    def _format_ref_currency(self, amount):
        self.ensure_one()
        val = amount or 0.0
        formatted = "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
        fiscal_curr = self.move_id._get_l10n_ve_ta_multicurrency_fiscal_id_dynamic()
        symbol = fiscal_curr.symbol or fiscal_curr.name or ''
        return f"{formatted} {symbol}"


