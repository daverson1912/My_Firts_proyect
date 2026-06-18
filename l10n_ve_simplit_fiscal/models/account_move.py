# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging
import requests

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    l10n_ve_partner_retention_type = fields.Selection(
        selection=[('75', '75%'), ('100', '100%')],
        string='Porcentaje de Retención',
        compute='_compute_l10n_ve_partner_retention_type',
        help='Tipo de retención de IVA que aplica a este documento.',
    )

    @api.depends('partner_id', 'move_type')
    def _compute_l10n_ve_partner_retention_type(self):
        for move in self:
            if move.move_type in ('in_invoice', 'in_refund'):
                move.l10n_ve_partner_retention_type = move.partner_id.l10n_ve_supplier_retention_type
            else:
                config = self.env['simplitfiscal.config'].search([('company_id', '=', move.company_id.id)], limit=1)
                move.l10n_ve_partner_retention_type = config.default_retention_type if config else False

    l10n_ve_islr_provider_type_id = fields.Many2one(
        'islr.provider.type',
        compute='_compute_l10n_ve_islr_provider_type_id',
        string='Beneficiario de Pago',
        readonly=True,
        store=False,
    )

    @api.depends('partner_id', 'move_type')
    def _compute_l10n_ve_islr_provider_type_id(self):
        for move in self:
            if move.move_type in ('in_invoice', 'in_refund'):
                move.l10n_ve_islr_provider_type_id = move.partner_id.l10n_ve_islr_provider_type_id
            else:
                config = self.env['simplitfiscal.config'].search([('company_id', '=', move.company_id.id)], limit=1)
                move.l10n_ve_islr_provider_type_id = config.islr_provider_type_id if config else False

    l10n_ve_control_number = fields.Char(
        string='Nro de Control',
        help='Número de control del documento físico.',
        copy=False,
    )

    l10n_ve_supplier_invoice_number = fields.Char(
        string='Nro Factura Proveedor',
        help='Número de la factura física del proveedor.',
        copy=False,
    )
    
    l10n_ve_wh_iva_count = fields.Integer(
        compute='_compute_wh_iva_count',
        string='Comprobantes de Retención',
        help='Número de comprobantes de retención generados para esta factura.',
    )
    
    l10n_ve_wh_iva_state = fields.Selection(
        selection=[
            ('draft', 'Sin procesar'),
            ('posted', 'Publicada'),
            ('declared', 'Declarada'),
        ],
        compute='_compute_wh_iva_state',
        string='Estado de Retención',
        help='Estado del comprobante de retención asociado a esta factura.',
    )

    l10n_ve_wh_islr_count = fields.Integer(
        compute='_compute_wh_islr_count',
        string='Retenciones ISLR',
    )
    
    l10n_ve_wh_islr_state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('posted', 'Publicado'),
            ('declared', 'Declarado'),
        ],
        compute='_compute_wh_islr_state',
        string='Estado ISLR',
    )

    def _get_islr_line_calculation_amount(self, line):
        """Hook genérico: Retorna el monto bruto de la línea en la moneda del cálculo (USD/VES)"""
        self.ensure_one()
        return line.price_subtotal

    def _process_islr_line_calculated_amounts(self, line, res_item):
        """Hook genérico: Procesa y guarda los montos calculados por el API en los campos nativos"""
        self.ensure_one()
        line.l10n_ve_islr_amount_line = res_item.get('retentionAmount', 0.0)
        line.l10n_ve_islr_subject_amount = res_item.get('subjectAmount', 0.0)
        line.l10n_ve_islr_subject_percentage = res_item.get('subject_amount_percentage', 0.0)
        line.l10n_ve_islr_base_retention_amount = res_item.get('baseRetentionAmount', 0.0)
        line.l10n_ve_islr_retention_percentage = res_item.get('retentionPercentage', 0.0)
        line.l10n_ve_islr_subtrahend = res_item.get('subtrahend', 0.0)
        line.l10n_ve_islr_fiscal_code = res_item.get('fiscalCode', '')


    l10n_ve_islr_amount = fields.Monetary(
        string='Retención ISLR',
        readonly=True,
        store=True,
        help='Monto total de retención de ISLR calculado por el API.',
    )

    l10n_ve_iva_retentions_summary = fields.Json(
        compute='_compute_l10n_ve_iva_retentions_summary',
        string='Resumen Retenciones IVA',
        help='Contiene el detalle de las retenciones de IVA para mostrarse por separado.',
    )

    l10n_ve_amount_to_pay = fields.Monetary(
        string='Cantidad por pagar',
        compute='_compute_l10n_ve_amount_to_pay',
        store=True,
        help='Monto neto a pagar después de ISLR y retenciones de IVA.',
    )

    # ========== RESUMEN FISCAL (reemplaza tax_totals cuando multicurrency no está instalado) ==========

    l10n_ve_show_summary = fields.Boolean(
        compute='_compute_l10n_ve_show_summary',
        store=False,
    )
    l10n_ve_doc_taxable_amount   = fields.Monetary(string='Gravable',      currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_exempt_amount    = fields.Monetary(string='Exento',        currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_discount_amount  = fields.Monetary(string='Descuento',     currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_subtotal         = fields.Monetary(string='Subtotal',      currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_gross_iva        = fields.Monetary(string='IVA',           currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_total            = fields.Monetary(string='Total',         currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_ret_iva          = fields.Monetary(string='Ret. IVA',      currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_ret_islr         = fields.Monetary(string='Ret. ISLR',     currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_igtf             = fields.Monetary(string='Impuesto IGTF', currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')
    l10n_ve_doc_amount_to_pay    = fields.Monetary(string='Monto a Pagar', currency_field='currency_id', compute='_compute_l10n_ve_doc_amounts')

    @api.depends('move_type')
    def _compute_l10n_ve_show_summary(self):
        for move in self:
            move.l10n_ve_show_summary = move.move_type in (
                'in_invoice', 'in_refund', 'out_invoice', 'out_refund'
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
    )
    def _compute_l10n_ve_doc_amounts(self):
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
                move.l10n_ve_doc_taxable_amount = move.l10n_ve_doc_exempt_amount = 0.0
                move.l10n_ve_doc_discount_amount = move.l10n_ve_doc_subtotal = 0.0
                move.l10n_ve_doc_gross_iva = move.l10n_ve_doc_total = 0.0
                move.l10n_ve_doc_ret_iva = move.l10n_ve_doc_ret_islr = 0.0
                move.l10n_ve_doc_igtf = 0.0
                move.l10n_ve_doc_amount_to_pay = 0.0
                continue

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
                    gross_iva += sum(t['amount'] for t in tax_res.get('taxes', []) if t['amount'] > 0)
                else:
                    exempt += ps

                if line.discount:
                    nominal = (line.quantity or 0.0) * (line.price_unit or 0.0)
                    discount += max(nominal - ps, 0.0)

            total_fiscal = subtotal + gross_iva
            is_refund    = move.move_type in ('in_refund', 'out_refund')
            ret_iva      = 0.0 if is_refund else (net_total - subtotal) - gross_iva
            islr         = 0.0 if is_refund else (move.l10n_ve_islr_amount or 0.0)
            igtf         = move.l10n_ve_igtf_amount or 0.0

            move.l10n_ve_doc_taxable_amount  = taxable
            move.l10n_ve_doc_exempt_amount   = exempt
            move.l10n_ve_doc_discount_amount = discount
            move.l10n_ve_doc_subtotal        = subtotal
            move.l10n_ve_doc_gross_iva       = gross_iva
            move.l10n_ve_doc_total           = total_fiscal
            move.l10n_ve_doc_ret_iva         = ret_iva
            move.l10n_ve_doc_ret_islr        = -abs(islr) if islr else 0.0
            move.l10n_ve_doc_igtf            = igtf
            move.l10n_ve_doc_amount_to_pay   = total_fiscal + ret_iva - abs(islr) - igtf

    # ========== CAMPOS PARA LIBRO DE VENTAS E IGTF ==========
    
    l10n_ve_has_igtf = fields.Boolean(
        string='Maneja IGTF',
        default=False,
        copy=False,
        help='Indica si la factura maneja el Impuesto a las Grandes Transacciones Financieras.',
    )
    
    l10n_ve_igtf_amount = fields.Monetary(
        string='Monto IGTF',
        currency_field='currency_id',
        copy=False,
        help='Monto transaccional del IGTF.',
    )
    
    l10n_ve_igtf_percentage = fields.Float(
        string='% IGTF',
        default=3.0,
        copy=False,
        help='Porcentaje de IGTF aplicado.',
    )

    l10n_ve_igtf_base = fields.Monetary(
        string='Base IGTF',
        currency_field='currency_id',
        copy=False,
        help='Monto total de la factura que sirve de base para el cálculo del IGTF.',
    )
    
    l10n_ve_fiscal_invoice_number = fields.Char(
        string='Nro Factura Fiscal',
        copy=False,
    )

    l10n_ve_fiscal_z_number = fields.Char(
        string='Nro de Reporte Z',
        copy=False,
    )

    l10n_ve_fiscal_printer_serial = fields.Char(
        string='Serial Impresora Fiscal',
        copy=False,
    )

    l10n_ve_fiscal_config_type = fields.Selection([
        ('free_form', 'Forma Libre'),
        ('fiscal_printer', 'Impresora Fiscal'),
        ('digital_invoice', 'Facturación Digital'),
    ], string='Tipo Config. Fiscal',
       compute='_compute_l10n_ve_fiscal_config_type',
    )

    @api.depends('company_id')
    def _compute_l10n_ve_fiscal_config_type(self):
        for move in self:
            config = self.env['simplitfiscal.config'].search([
                ('company_id', '=', move.company_id.id)
            ], limit=1)
            move.l10n_ve_fiscal_config_type = config.l10n_ve_fiscal_config_type if config else 'free_form'

    l10n_ve_iva_retentions_summary_html = fields.Html(
        compute='_compute_l10n_ve_iva_retentions_summary',
        string='Retenciones IVA HTML',
    )

    
    def button_draft(self):
        """
        Bloquea el regreso a borrador si ya se declaró alguna retención.
        Si se permite, sincroniza las retenciones para que también vuelvan a borrador.
        """
        for move in self:
            # 1. Verificar IVA
            iva_ret = self.env['account.wh.iva'].search([('move_id', '=', move.id), ('state', '!=', 'cancel')])
            if any(r.state == 'declared' for r in iva_ret):
                raise ValidationError(_(
                    "No se puede revertir a borrador porque la factura %s ya tiene una retención de IVA declarada ante el SENIAT."
                ) % move.name)
            
            # 2. Verificar ISLR
            islr_ret = self.env['account.wh.islr'].search([('move_id', '=', move.id), ('state', '!=', 'cancel')])
            if any(r.state == 'declared' for r in islr_ret):
                raise ValidationError(_(
                    "No se puede revertir a borrador porque la factura %s ya tiene una retención de ISLR declarada ante el SENIAT."
                ) % move.name)

            # 3. Sincronizar estados (IVA/ISLR pasan a draft)
            iva_ret.write({'state': 'draft'})
            islr_ret.write({'state': 'draft'})

        return super(AccountMove, self).button_draft()

    def action_post(self):
        """
        Wrapper para el proceso de publicación.
        """
        return super().action_post()

    # -------------------------------------------------------------------------
    # MÉTODOS DE APOYO
    # -------------------------------------------------------------------------

    def _inject_islr_integrated_line(self):
        """
        Modifica las líneas de la factura en borrador para incluir la retención.
        Reduce la cuenta por pagar/cobrar y añade la cuenta de ISLR configurada.
        Es idempotente: actualiza líneas existentes en lugar de eliminarlas.
        """
        self.ensure_one()
        if self.state != 'draft':
            return

        config = self.env['simplitfiscal.config'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        is_purchase = self.move_type in ('in_invoice', 'in_refund')
        is_sale = self.move_type in ('out_invoice', 'out_refund')

        if not is_purchase and not is_sale:
            return

        if is_purchase:
            islr_account = config.l10n_ve_islr_account_id_purchase if config else False
            if not islr_account:
                raise ValidationError(_("Debe configurar la Cuenta Contable ISLR (Compras) en la configuración fiscal para el asiento integrado."))
        else:
            islr_account = config.l10n_ve_islr_account_id_sale if config else False
            if not islr_account:
                raise ValidationError(_("Debe configurar la Cuenta Contable ISLR (Ventas) en la configuración fiscal para el asiento integrado."))

        # 1. Identificar líneas existentes y línea de contrapartida (Payable o Receivable)
        existing_islr_lines = self.line_ids.filtered(
            lambda l: l.account_id == islr_account and l.display_type == 'tax'
        )
        
        if is_purchase:
            counterpart_line = self.line_ids.filtered(lambda l: l.account_type == 'liability_payable')
        else:
            counterpart_line = self.line_ids.filtered(lambda l: l.account_type == 'asset_receivable')

        if not counterpart_line:
            _logger.warning(f"[FISCAL-ISLR] No se encontró línea de contrapartida (Payable/Receivable) para {self.name}")
            return

        islr_amount = self.l10n_ve_islr_amount  # En moneda de la factura (VEF)
        counter_l = counterpart_line[0]

        # Convertir a moneda de la compañía para manipular balance/credit/debit
        company_currency = self.company_id.currency_id
        invoice_currency = self.currency_id
        ref_date = self.invoice_date or fields.Date.context_today(self)
        is_multicurrency = invoice_currency and invoice_currency != company_currency
        if is_multicurrency:
            islr_bal = invoice_currency._convert(islr_amount, company_currency, self.company_id, ref_date)
        else:
            islr_bal = islr_amount

        # in_invoice y out_refund van al lado crédito; in_refund y out_invoice al débito
        is_credit_side = self.move_type in ('in_invoice', 'out_refund')

        # 2. Lógica de Actualización / Inserción
        if existing_islr_lines:
            line_to_update = existing_islr_lines[0]
            old_bal = line_to_update.credit if is_credit_side else line_to_update.debit
            old_ac  = abs(line_to_update.amount_currency)
            delta_bal = old_bal - islr_bal
            delta_ac  = old_ac - islr_amount

            if is_credit_side:
                counter_upd = {'credit': counter_l.credit + delta_bal}
                line_upd    = {'credit': islr_bal, 'debit': 0.0}
                if is_multicurrency:
                    counter_upd['amount_currency'] = counter_l.amount_currency - delta_ac
                    line_upd['amount_currency'] = -islr_amount
            else:
                counter_upd = {'debit': counter_l.debit + delta_bal}
                line_upd    = {'debit': islr_bal, 'credit': 0.0}
                if is_multicurrency:
                    counter_upd['amount_currency'] = counter_l.amount_currency + delta_ac
                    line_upd['amount_currency'] = islr_amount

            counter_l.with_context(check_move_validity=False).write(counter_upd)
            line_to_update.with_context(check_move_validity=False).write(line_upd)

            for extra_line in existing_islr_lines[1:]:
                extra_line.with_context(check_move_validity=False).write({'debit': 0.0, 'credit': 0.0, 'amount_currency': 0.0})

        elif islr_amount > 0:
            names = {
                'in_invoice':  f"Retención ISLR {self.name or ''}",
                'in_refund':   f"Reverso Retención ISLR {self.name or ''}",
                'out_invoice': f"Retención ISLR {self.name or ''}",
                'out_refund':  f"Reverso Retención ISLR {self.name or ''}",
            }

            if is_credit_side:
                counter_upd = {'credit': counter_l.credit - islr_bal}
                vals = {'debit': 0.0, 'credit': islr_bal}
                if is_multicurrency:
                    counter_upd['amount_currency'] = counter_l.amount_currency + islr_amount
                    vals['amount_currency'] = -islr_amount
            else:
                counter_upd = {'debit': counter_l.debit - islr_bal}
                vals = {'debit': islr_bal, 'credit': 0.0}
                if is_multicurrency:
                    counter_upd['amount_currency'] = counter_l.amount_currency - islr_amount
                    vals['amount_currency'] = islr_amount

            counter_l.with_context(check_move_validity=False).write(counter_upd)

            new_line = {
                **vals,
                'name': names[self.move_type],
                'partner_id': self.partner_id.id,
                'account_id': islr_account.id,
                'date_maturity': self.invoice_date_due or self.invoice_date or fields.Date.context_today(self),
                'display_type': 'tax',
            }
            if is_multicurrency:
                new_line['currency_id'] = invoice_currency.id

            self.with_context(check_move_validity=False).write({
                'line_ids': [(0, 0, new_line)]
            })

        _logger.info(f"[ISLR] Inyectada/Actualizada línea de retención integrada en move {self.id}")

    def _get_ve_bolivar_currency(self):
        """Retorna la moneda Bolívar activa (VED o VEF). Fallback: moneda de la factura."""
        for code in ('VED', 'VEF'):
            currency = self.env['res.currency'].search(
                [('name', '=', code), ('active', '=', True)], limit=1
            )
            if currency:
                return currency
        return self.currency_id

    def _to_bolivar(self, amount, bolivar_currency):
        """Convierte un monto de la moneda de la factura a Bolívares."""
        if not bolivar_currency or self.currency_id == bolivar_currency:
            return amount
        ref_date = self.invoice_date or fields.Date.context_today(self)
        return self.currency_id._convert(amount, bolivar_currency, self.company_id, ref_date)

    def _create_islr_withholding(self):
        """
        Crea el registro de retención de ISLR vinculado a la factura y sus líneas de detalle.
        Los montos siempre se guardan en Bolívares (VED/VEF).
        """
        self.ensure_one()

        existing = self.env['account.wh.islr'].search([('move_id', '=', self.id)], limit=1)
        if existing and existing.state not in ('draft',):
            return existing  # publicado/declarado: no tocar

        bs = self._get_ve_bolivar_currency()

        def bsf(amount):
            return self._to_bolivar(amount, bs)

        amount_taxable_base = sum(self.invoice_line_ids.filtered(lambda l: l.l10n_ve_islr_amount_line > 0).mapped('price_subtotal'))
        amount_exempt = sum(self.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and not l.l10n_ve_islr_amount_line > 0).mapped('price_subtotal'))
        amount_total_invoice = self.amount_untaxed + self._calculate_tax_base()
        total_ret_iva = self._calculate_total_retention()
        amount_to_pay = amount_total_invoice - total_ret_iva - self.l10n_ve_islr_amount
        wh_type = 'refund' if self.move_type == 'in_refund' else 'invoice'

        wh_vals = {
            'currency_id': bs.id,
            'amount_total_ret': bsf(self.l10n_ve_islr_amount),
            'amount_taxable_base': bsf(amount_taxable_base),
            'amount_exempt': bsf(amount_exempt),
            'amount_total_invoice': bsf(amount_total_invoice),
            'amount_to_pay': bsf(amount_to_pay),
            'wh_type': wh_type,
        }

        if existing:
            # Borrador existente: actualizar valores y recrear líneas
            existing.write(wh_vals)
            existing.line_ids.unlink()
            wh_islr = existing
        else:
            wh_vals.update({
                'partner_id': self.partner_id.id,
                'move_id': self.id,
                'api_transaction_id': False,
                'date': self.invoice_date or fields.Date.context_today(self),
                'company_id': self.company_id.id,
                'type': 'purchase' if self.move_type in ('in_invoice', 'in_refund') else 'sale',
            })
            wh_islr = self.env['account.wh.islr'].create(wh_vals)

        for line in self.invoice_line_ids.filtered(lambda l: l.l10n_ve_islr_amount_line > 0):
            concept = line.product_id.l10n_ve_islr_rate_id
            self.env['account.wh.islr.line'].create({
                'islr_id': wh_islr.id,
                'concept_id': concept.id if concept else False,
                'product_id': line.product_id.id,
                'move_line_id': line.id,
                'base_amount': bsf(line.price_subtotal),
                'subject_amount': bsf(line.l10n_ve_islr_subject_amount),
                'subject_amount_percentage': line.l10n_ve_islr_subject_percentage,
                'base_retention_amount': bsf(line.l10n_ve_islr_base_retention_amount),
                'retention_percentage': line.l10n_ve_islr_retention_percentage,
                'subtrahend': bsf(line.l10n_ve_islr_subtrahend),
                'retention_amount': bsf(line.l10n_ve_islr_amount_line),
                'fiscal_code': line.l10n_ve_islr_fiscal_code,
            })

        return wh_islr
    
    def _create_withholding_voucher(self):
        """
        Crea comprobante de retención si la factura tiene retenciones de IVA.
        
        El comprobante se crea en estado 'draft' y será procesado posteriormente
        vía interfaz unificador para obtener numeración desde API.
        """
        self.ensure_one()
        
        # Verificar que no exista ya un comprobante
        voucher_type = 'purchase' if self.move_type in ('in_invoice', 'in_refund') else 'sale'
        existing = self.env['account.wh.iva'].search([
            ('move_id', '=', self.id),
            ('type', '=', voucher_type)
        ], limit=1)
        
        if existing and existing.state not in ('draft',):
            return  # publicado/declarado: no tocar
        
        # Calcular montos para las 15 columnas
        amount_total_ret = self._calculate_total_retention()
        _logger.warning(f"[FISCAL] Monto total de retención calculado para {self.name}: {amount_total_ret}")
        
        amount_base_iva = self._calculate_tax_base()  # El campo viejo que guarda el monto del IVA
        _logger.warning(f"[FISCAL] Base imponible de IVA calculada para {self.name}: {amount_base_iva}")
        
        # Nuevos cálculos detallados
        amount_exempt = 0.0
        amount_taxable_base = 0.0
        tax_aliquot = 0.0

        for line in self.invoice_line_ids:
            # Obtener todos los impuestos aplicados (incluyendo hijos de grupos)
            all_taxes = line.tax_ids
            if any(t.amount_type == 'group' for t in all_taxes):
                # Si hay grupos, expandirlos (manualmente para ser compatible con varias versiones)
                flattened_taxes = self.env['account.tax']
                for t in all_taxes:
                    if t.amount_type == 'group':
                        flattened_taxes |= t.children_tax_ids
                    else:
                        flattened_taxes |= t
                all_taxes = flattened_taxes

            # Líneas gravadas con IVA: tienen al menos un impuesto con monto > 0
            iva_taxes = all_taxes.filtered(lambda t: t.amount > 0)
            
            if iva_taxes:
                amount_taxable_base += line.price_subtotal
                if not tax_aliquot:
                    tax_aliquot = iva_taxes[0].amount
            else:
                # Si no tiene impuestos o todos son <= 0 (retenciones/exentos), es exento
                amount_exempt += line.price_subtotal

        # % de Retención
        retention_percentage = 0.0
        if amount_base_iva > 0:
            retention_percentage = (amount_total_ret / amount_base_iva) * 100

        if amount_total_ret <= 0:
            _logger.debug(
                f"[FISCAL] Factura {self.name} no tiene retenciones de IVA, "
                f"no se crea comprobante"
            )
            return
        
        # Determinar tipo de documento
        wh_type = 'refund' if self.move_type in ('in_refund', 'out_refund') else 'invoice'
        
        # Buscar Factura y Retención de Origen (Solo para Notas de Crédito)
        parent_wh_iva_id = False
        if wh_type == 'refund' and self.reversed_entry_id:
            # Buscar la retención asociada a la factura original
            parent_wh_voucher = self.env['account.wh.iva'].search([
                ('move_id', '=', self.reversed_entry_id.id),
                ('type', '=', voucher_type)
            ], limit=1)
            
            if parent_wh_voucher:
                parent_wh_iva_id = parent_wh_voucher.id
                _logger.info(f"[FISCAL] Encontrada retención origen ID={parent_wh_iva_id} para NC {self.name}")
        
        bs = self._get_ve_bolivar_currency()

        def bsf(amount):
            return self._to_bolivar(amount, bs)

        # Crear comprobante con todos los campos para el reporte (montos en Bolívares)
        withholding_vals = {
            'partner_id': self.partner_id.id,
            'move_id': self.id,
            'date': self.invoice_date or fields.Date.context_today(self),
            'amount_base': bsf(amount_base_iva),
            'amount_total_ret': bsf(amount_total_ret),
            'company_id': self.company_id.id,
            'currency_id': bs.id,
            'state': 'draft',
            'wh_type': wh_type,
            'type': voucher_type,
            'parent_wh_iva_id': parent_wh_iva_id,

            # --- NUEVOS CAMPOS ---
            'control_number': getattr(self, 'l10n_ve_control_number', False),
            'operation_type': False,
            'amount_total_signed': bsf(self.amount_total),
            'amount_total_invoice': bsf(amount_taxable_base + amount_exempt + amount_base_iva),
            'amount_exempt': bsf(amount_exempt),
            'amount_taxable_base': bsf(amount_taxable_base),
            'tax_aliquot': tax_aliquot,
            'amount_vat_tax': bsf(amount_base_iva),
            'retention_percentage': retention_percentage,
            'supplier_invoice_number': self.l10n_ve_supplier_invoice_number,
        }
        
        if existing:
            existing.write(withholding_vals)
            wh_voucher = existing
        else:
            wh_voucher = self.env['account.wh.iva'].create(withholding_vals)
        
        _logger.info(
            f"[FISCAL] Comprobante de retención ({wh_type}) creado con detalle completo: "
            f"ID={wh_voucher.id}, Factura={self.name}, "
            f"Base={amount_taxable_base}, IVA={amount_base_iva}, Retenido={amount_total_ret}"
        )
        
        return wh_voucher
    
    def _calculate_total_retention(self):
        """
        Calcula el monto total de IVA retenido en la factura.
        
        Busca líneas de impuestos que sean retenciones (impuestos con amount negativo
        y marcados como is_simplit_tax).
        
        Returns:
            float: Monto total retenido (valor absoluto)
        """
        self.ensure_one()
        
        total_retention = 0.0
        
        for line in self.line_ids:
            # Buscar líneas de impuestos (Odoo 18: tax_line_id está en account.move.line)
            if line.tax_line_id:
                tax = line.tax_line_id
                _logger.warning(f"[FISCAL] Evaluando línea de impuesto contable: {tax.name} (Amount: {tax.amount}, Simplit: {getattr(tax, 'is_simplit_tax', 'N/A')})")
                
                # Verificar si es un impuesto de retención de Simplit
                # Usamos el flag is_simplit_tax o detectamos si el monto es negativo y es de tipo Simplit
                if (hasattr(tax, 'is_simplit_tax') and tax.is_simplit_tax) or tax.simplit_tax_type:
                    if tax.amount < 0:
                        # amount_currency = valor en moneda de la factura (VEF/VED)
                        val = abs(line.amount_currency)
                        total_retention += val
                        _logger.warning(f"[FISCAL] -> Sumando retención: {val} (Total acumulado: {total_retention})")
        
        return total_retention
    
    def _calculate_tax_base(self):
        """
        Calcula el monto total del IVA de la factura (base imponible).
        
        La base es el monto total de IVA aplicado a la factura, sobre el cual
        se calcula la retención.
        
        Returns:
            float: Monto total de IVA
        """
        self.ensure_one()
        
        total_tax = 0.0
        
        for line in self.line_ids:
            # Buscar líneas de impuestos que sean IVA (no retenciones)
            if line.tax_line_id:
                tax = line.tax_line_id
                
                # IVA normal tiene amount positivo (ej: 16%)
                # Retenciones tienen amount negativo (ej: -12%)
                # Solo contar impuestos positivos (IVA base)
                if tax.amount > 0:
                    total_tax += abs(line.amount_currency)
        
        return total_tax
    
    def action_calculate_islr_retention(self, raise_error=False):
        """
        Calcula la retención de ISLR consultando el API externo.
        """
        for move in self:
            # Solo para facturas de compra (proveedor sujeto) o venta (cliente agente)
            is_purchase = move.move_type in ('in_invoice', 'in_refund')
            is_sale = move.move_type in ('out_invoice', 'out_refund')
            
            if is_purchase:
                if not move.partner_id.l10n_ve_is_islr_payer:
                    move.l10n_ve_islr_amount = 0.0
                    continue
            elif not is_sale:
                move.l10n_ve_islr_amount = 0.0
                continue

            # Filtrar líneas con productos que aplican ISLR
            islr_lines = move.invoice_line_ids.filtered(
                lambda l: l.product_id and l.product_id.l10n_ve_apply_islr and l.product_id.l10n_ve_islr_rate_id
            )
            
            if not islr_lines:
                move.l10n_ve_islr_amount = 0.0
                continue

            # Obtener configuración fiscal
            config = self.env['simplitfiscal.config'].search([('company_id', '=', move.company_id.id)], limit=1)
            
            # Preparar Payload según flujo
            if is_purchase:
                provider_type = move.partner_id.l10n_ve_islr_provider_type_id
                provider_name = (move.partner_id.name or "")[:80]
                provider_odoo_id = move.partner_id.id
            else:
                # Ventas: el beneficiario (provider) somos nosotros
                provider_type = config.islr_provider_type_id
                provider_name = (move.company_id.name or "")[:80]
                provider_odoo_id = move.company_id.id

            if not provider_type:
                _logger.warning(f"[FISCAL-ISLR] No se encontró Tipo de Beneficiario para {provider_name}")
                continue

            payload = {
                "providerType": {
                    "guid": int(provider_type.guid) if provider_type.guid and provider_type.guid.isdigit() else provider_type.guid,
                    "code": provider_type.code
                },
                "items": [],
                "providerName": provider_name,
                "providerOdooId": provider_odoo_id,
            }

            line_map = {} # Para mapear respuesta a líneas
            for line in islr_lines:
                # El GUID de retención debe ser numérico según especificación del API
                ret_guid = line.product_id.l10n_ve_islr_rate_id.guid
                try:
                    ret_guid_int = int(ret_guid) if ret_guid and ret_guid.isdigit() else ret_guid
                except:
                    ret_guid_int = ret_guid

                # Obtener el monto de cálculo vía hook genérico
                amount_calc = round(move._get_islr_line_calculation_amount(line), 2)

                item_data = {
                    "amount": amount_calc,
                    "retentionTypeGuid": ret_guid_int
                }
                payload["items"].append(item_data)
                
                # La llave usa el monto del cálculo para que coincida con la respuesta del API
                key = f"{ret_guid}_{amount_calc:.2f}"
                _logger.info(f"ISLR Calc: Generando llave para linea: {key}")
                if key not in line_map:
                    line_map[key] = self.env['account.move.line']
                line_map[key] |= line

            # Llamar API
            try:
                from .utils import get_api_url
                api_host = get_api_url()
                url = f"{api_host.rstrip('/')}/api/v1/master-data/calculate-retention" if api_host else ""
                
                # Obtener API Key de la configuración fiscal
                config = self.env['simplitfiscal.config'].search([('company_id', '=', move.company_id.id)], limit=1)
                api_key = config.ta_api_key if config else False

                headers = {}
                if api_key:
                    headers['X-API-Key'] = api_key

                _logger.warning(f"[FISCAL-ISLR-URL] {url}")
                _logger.warning(f"[FISCAL-ISLR-PAYLOAD] {payload}")
                
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                _logger.warning(f"[FISCAL-ISLR-STATUS] {response.status_code}")
                _logger.warning(f"[FISCAL-ISLR-RESPONSE] {response.text}")
                
                try:
                    res_data = response.json()
                except:
                    res_data = {}

                # 1. Validar Status HTTP
                if response.status_code not in (200, 201):
                    msg = res_data.get('message') or _("Error de comunicación con el Servicio Fiscal (Status: %s).") % response.status_code
                    
                    _logger.error(f"ISLR Calc ERROR: {msg}")
                    if raise_error:
                        raise UserError(msg)
                    continue

                # 2. Validar éxito o error lógico según campo 'error'
                if res_data.get('error') == 0:
                    for item_res in res_data.get('data', []):
                        r_guid = item_res.get('retentionTypeGuid')
                        r_amount_item = item_res.get('itemAmount')
                        
                        # Buscar línea(s) correspondiente(s) con el mismo formato de llave
                        key = f"{r_guid}_{r_amount_item:.2f}"
                        _logger.info(f"ISLR Calc: Buscando llave en respuesta: {key}")
                        lines = line_map.get(key)
                        if lines:
                            for l in lines:
                                # El API devuelve valores por ítem — cada línea recibe el mismo valor
                                move._process_islr_line_calculated_amounts(l, item_res)
                                _logger.info(f"ISLR Calc: Linea {l.id} procesada con {l.l10n_ve_islr_amount_line} en moneda documento")
                    
                    # Guardar el monto total retenido de ISLR en el documento
                    move.l10n_ve_islr_amount = sum(move.invoice_line_ids.mapped('l10n_ve_islr_amount_line'))
                    _logger.info(f"ISLR Calc SUCCESS: Cálculo finalizado para {move.name}. Total Retenido (Doc Currency): {move.l10n_ve_islr_amount}")
                    
                    # Inyectar línea contable integrada en borrador para visualización inmediata
                    if move.state == 'draft' and move.l10n_ve_islr_amount > 0:
                        move._inject_islr_integrated_line()
                else:
                    msg = res_data.get('message', _("Error desconocido en el Servicio Fiscal."))
                    _logger.warning(f"ISLR Calc WARNING: {msg}")
                    if raise_error:
                        raise UserError(msg)

            except Exception as e:
                if isinstance(e, UserError):
                    raise e
                _logger.error(f"ISLR Calc EXCEPTION: {str(e)}")
                msg = _("No se pudo establecer conexión con el Servicio Fiscal. Verifique la configuración de red y el estado del servidor.")
                if raise_error:
                    raise UserError(msg)

    @api.depends('line_ids')
    def _compute_wh_iva_count(self):
        """
        Calcula el número de comprobantes de retención asociados a esta factura.
        """
        for move in self:
            move.l10n_ve_wh_iva_count = self.env['account.wh.iva'].search_count([
                ('move_id', '=', move.id)
            ])
    
    @api.depends('line_ids')
    def _compute_wh_iva_state(self):
        """
        Calcula el estado del comprobante de retención asociado a esta factura.
        """
        for move in self:
            # Buscar comprobante de retención
            voucher = self.env['account.wh.iva'].search([
                ('move_id', '=', move.id)
            ], limit=1)
            
            if voucher:
                # Mapear 'done' a 'posted' para compatibilidad en el UI
                move.l10n_ve_wh_iva_state = 'posted' if voucher.state == 'done' else voucher.state
            else:
                move.l10n_ve_wh_iva_state = False
    
    def action_view_withholding_vouchers(self):
        """
        Abre la vista de comprobantes de retención asociados a esta factura.
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'l10n_ve_simplit_fiscal.action_wh_iva_unifier'
        )
        vouchers = self.env['account.wh.iva'].search([('move_id', '=', self.id)])
        if len(vouchers) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = vouchers.id
        else:
            action['domain'] = [('move_id', '=', self.id)]
        action['context'] = {
            'default_move_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_date': self.invoice_date,
        }
        return action

    @api.depends('line_ids')
    def _compute_wh_islr_count(self):
        for move in self:
            move.l10n_ve_wh_islr_count = self.env['account.wh.islr'].search_count([
                ('move_id', '=', move.id)
            ])

    @api.depends('line_ids')
    @api.onchange('invoice_line_ids', 'partner_id')
    def _onchange_islr_trigger(self):
        """
        Disparador automtico para calcular ISLR en tiempo real
        mientras se edita la factura en borrador.
        """
        if self.state == 'draft' and self.move_type in ('in_invoice', 'in_refund'):
            # Llamamos al mtodo que ya existe y que consulta al API
            if hasattr(self, 'action_calculate_islr_retention'):
                self.action_calculate_islr_retention(raise_error=True)

    @api.depends('line_ids')
    def _compute_wh_islr_state(self):
        for move in self:
            v_type = 'purchase' if move.move_type in ('in_invoice', 'in_refund') else 'sale'
            voucher = self.env['account.wh.islr'].search([
                ('move_id', '=', move.id),
                ('type', '=', v_type)
            ], limit=1)
            if voucher:
                # Mapear 'done' a 'posted' para compatibilidad en el UI
                move.l10n_ve_wh_islr_state = 'posted' if voucher.state == 'done' else voucher.state
            else:
                move.l10n_ve_wh_islr_state = False

    def action_view_islr_withholding(self):
        self.ensure_one()
        v_type = 'purchase' if self.move_type in ('in_invoice', 'in_refund') else 'sale'
        action = {
            'name': _('Retenciones ISLR'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.wh.islr',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id), ('type', '=', v_type)],
            'context': {'default_move_id': self.id, 'default_type': v_type},
        }
        vouchers = self.env['account.wh.islr'].search([('move_id', '=', self.id), ('type', '=', v_type)])
        if len(vouchers) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': vouchers.id,
            })
        return action

    @api.depends('line_ids', 'l10n_ve_islr_amount', 'amount_total', 'tax_totals')
    def _compute_l10n_ve_amount_to_pay(self):
        for move in self:
            total = move.tax_totals.get('total_amount_currency', move.amount_total) if move.tax_totals else move.amount_total
            move.l10n_ve_amount_to_pay = total

    @api.depends('l10n_ve_islr_amount', 'currency_id')
    def _compute_tax_totals(self):
        """
        Inyectar ISLR en los totales de Odoo 18 y renombrar etiquetas de retención.
        """
        super()._compute_tax_totals()
        for move in self:
            if move.tax_totals and isinstance(move.tax_totals, dict):
                # Trabajamos sobre una copia para asegurar la detección de cambios
                totals = move.tax_totals.copy()
                
                # 1. Renombrar grupos de Retención de IVA existentes (Estándar de Odoo)
                for subtotal in totals.get('subtotals', []):
                    for group in subtotal.get('tax_groups', []):
                        g_name = group.get('group_name', '')
                        if g_name and 'Retención IVA' in g_name:
                            group['group_name'] = 'Ret. IVA'

                # 2. Inyectar Retención ISLR (Manual)
                islr_amount = getattr(move, 'l10n_ve_islr_amount', 0.0)
                if islr_amount > 0:
                    # Localizar el primer subtotal para inyectar la línea
                    subtotals = totals.get('subtotals', [])
                    if subtotals:
                        subtotal = subtotals[0]
                        if 'tax_groups' in subtotal:
                            # Evitar duplicados
                            if not any(g.get('id') == 99999 for g in subtotal['tax_groups']):
                                subtotal['tax_groups'].append({
                                    'id': 99999,
                                    'involved_tax_ids': [],
                                    'tax_amount_currency': -islr_amount,
                                    'tax_amount': -islr_amount,
                                    'base_amount_currency': totals.get('base_amount_currency', 0.0),
                                    'base_amount': totals.get('base_amount_currency', 0.0),
                                    'display_base_amount_currency': totals.get('base_amount_currency', 0.0),
                                    'display_base_amount': totals.get('base_amount_currency', 0.0),
                                    'group_name': 'Ret. ISLR',
                                    'group_label': False
                                })
                                # Ajustar totales finales
                                totals['total_amount_currency'] -= islr_amount
                                totals['total_amount'] -= islr_amount
                
                # Reasignar el diccionario modificado
                move.tax_totals = totals

    @api.depends('line_ids', 'l10n_ve_islr_amount', 'amount_total', 'tax_totals')
    def _compute_l10n_ve_iva_retentions_summary(self):
        for move in self:
            retentions = []
            html_content = '<div style="width: 100%;">'
            
            # 1. IVA Retentions
            for line in move.line_ids.filtered(lambda l: l.tax_line_id):
                tax = line.tax_line_id
                if (getattr(tax, 'is_simplit_tax', False) or tax.simplit_tax_type) and tax.amount < 0:
                    amount_fmt = move.currency_id.format(abs(line.balance))
                    retentions.append({
                        'name': tax.name,
                        'amount': abs(line.balance),
                        'tax_id': tax.id,
                    })
                    html_content += f'<div style="display: flex; justify-content: flex-end; gap: 40px; margin-bottom: 2px;">' \
                                    f'<span style="color: #666;">{tax.name}:</span> ' \
                                    f'<span style="color: #dc3545; font-weight: bold;">-{amount_fmt}</span>' \
                                    f'</div>'
            
            # 2. ISLR Retention - Movido al widget nativo tax_totals
            
            html_content += '</div>'
            move.l10n_ve_iva_retentions_summary = retentions
            move.l10n_ve_iva_retentions_summary_html = html_content if retentions else False


            # 1. Identificar nombres de grupos que corresponden a retenciones
            # Usamos el nuevo campo 'is_retention' para mayor precisión
            retention_groups_names = move.line_ids.filtered(
                lambda l: l.tax_line_id and (getattr(l.tax_line_id, 'is_retention', False) or l.tax_line_id.amount < 0)
            ).mapped('tax_line_id.tax_group_id.name')
            
            # Filtramos también por nombre si el campo no está marcado (fallback de seguridad)
            # El usuario mencionó que el 16% debe quedar arriba.
            # Los grupos de retención suelen tener "Ret" o valores negativos.

            # 2. Filtrar grupos de la visualización (Odoo 17+)
            # tax_totals['subtotals'] es una lista de diccionarios, cada uno con 'tax_groups'
            tax_amount_filtered = 0.0
            tax_amount_currency_filtered = 0.0
            
            # Se comenta la lógica de filtrado para que las retenciones permanezcan en el bloque de totales nativo
            # if 'subtotals' in move.tax_totals:
            #     for subtotal in move.tax_totals['subtotals']:
            #         new_groups = []
            #         for group in subtotal.get('tax_groups', []):
            #             g_name = group.get('group_name') or group.get('tax_group_name')
            #             if g_name in retention_groups_names:
            #                 tax_amount_filtered += group.get('tax_amount', 0.0)
            #                 tax_amount_currency_filtered += group.get('tax_amount_currency', 0.0)
            #                 continue
            #             new_groups.append(group)
            #         subtotal['tax_groups'] = new_groups
            
            # if 'total_amount' in move.tax_totals:
            #     move.tax_totals['total_amount'] -= tax_amount_filtered
            #     move.tax_totals['total_amount_currency'] -= tax_amount_currency_filtered
            
            move.tax_totals = move.tax_totals

    # -------------------------------------------------------------------------
    # OVERRIDES CORE (Movido al final para prioridad)
    # -------------------------------------------------------------------------

    def _post(self, soft=True):
        """
        Extensión del método de publicación para generar retenciones automáticas.
        Soporta flujos de Compras y Ventas (IVA/ISLR).
        """
        for move in self:
            is_fiscal = move.move_type in ('in_invoice', 'out_invoice')
            if is_fiscal:
                _logger.warning(f"[FISCAL] Iniciando proceso fiscal pre-post para {move.name}")
                # 1. Calcular ISLR vía API (Bloqueante si falla)
                move.action_calculate_islr_retention(raise_error=True)

                # 2. Inyectar línea contable integrada (Compras y Ventas)
                if move.l10n_ve_islr_amount > 0:
                    move._inject_islr_integrated_line()

        # 3. Publicación estándar de Odoo
        res = super()._post(soft=soft)

        # 4. Creación de registros informativos y comprobantes (solo facturas, no NC)
        for move in self:
            if move.move_type in ('in_invoice', 'out_invoice'):
                _logger.warning(f"[FISCAL] Generando comprobantes post-posteo para {move.name}")

                # Comprobante IVA
                move._create_withholding_voucher()

                # Comprobante ISLR
                if move.l10n_ve_islr_amount > 0:
                    move._create_islr_withholding()
        return res
