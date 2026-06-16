# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import logging
import xlsxwriter

_logger = logging.getLogger(__name__)

class AccountIvaPurchaseLedgerWizard(models.TransientModel):
    _name = 'account.iva.purchase.ledger.wizard'
    _description = 'Asistente de Libro de Compras IVA'

    company_id = fields.Many2one(
        'res.company', 
        string='Compañía', 
        required=True, 
        default=lambda self: self.env.company
    )
    date_from = fields.Date(
        string='Fecha Desde', 
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Date(
        string='Fecha Hasta', 
        required=True,
        default=fields.Date.context_today
    )
    
    # Campos para la descarga del archivo generado
    pdf_file = fields.Binary(string='Archivo PDF', readonly=True)
    pdf_filename = fields.Char(string='Nombre PDF', readonly=True)
    excel_file = fields.Binary(string='Archivo Excel', readonly=True)
    excel_filename = fields.Char(string='Nombre Excel', readonly=True)
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Generado')
    ], string='Estado', default='draft')

    def _get_ledger_data(self):
        """
        Obtiene y procesa los datos necesarios para el libro de compras.
        """
        self.ensure_one()
        Move = self.env['account.move']
        
        domain = [
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        
        moves = Move.search(domain, order='invoice_date asc, name asc')
        
        ledger_lines = []
        count = 1
        
        for move in moves:
            # Identificar tipo de documento
            doc_type = 'FAC'
            if move.move_type == 'in_refund':
                doc_type = 'NC'
            elif getattr(move, 'debit_origin_id', False):
                doc_type = 'ND'
            
            # Tipo de Transacción
            tran_type = '01-REG'
            if move.payment_state == 'reversed' or (move.amount_total == 0 and move.state == 'cancel'):
                tran_type = '03-ANUL'
            
            # Obtener todas las retenciones IVA del documento (puede haber una por alícuota)
            wh_iva_all = self.env['account.wh.iva'].search([
                ('move_id', '=', move.id),
                ('state', '!=', 'cancel')
            ])
            wh_iva = wh_iva_all[0] if wh_iva_all else False

            # Detección de importación por país del proveedor
            is_import = bool(move.partner_id.country_id and move.partner_id.country_id.code != 'VE')

            # Totales y Bases
            sign = -1 if move.move_type == 'in_refund' else 1

            def get_line_taxes(tax_ids):
                taxes = []
                for tax in tax_ids:
                    if tax.amount_type == 'group':
                        taxes.extend(get_line_taxes(tax.children_tax_ids))
                    else:
                        taxes.append(tax)
                return taxes

            if wh_iva_all:
                # Fuente principal: tablas de retención IVA (aplica con o sin multimoneda)
                total_with_iva = wh_iva.amount_total_invoice * sign

                base_16 = 0.0
                iva_16 = 0.0
                base_8 = 0.0
                iva_8 = 0.0
                exempt_amount = wh_iva.amount_exempt * sign
                wh_amount = 0.0

                for wh in wh_iva_all:
                    aliquot = int(round(wh.tax_aliquot))
                    if aliquot == 16:
                        base_16 += wh.amount_taxable_base * sign
                        iva_16 += wh.amount_vat_tax * sign
                    elif aliquot == 8:
                        base_8 += wh.amount_taxable_base * sign
                        iva_8 += wh.amount_vat_tax * sign
                    wh_amount += wh.amount_total_ret * sign

                taxable_base = base_16 + base_8
                iva_amount = iva_16 + iva_8

            else:
                # Fallback: factura sin retención — montos en Bolívares (VES)
                mc_installed = 'l10n_ve_ta_multicurrency_total_amount' in move._fields

                base_16 = 0.0
                iva_16 = 0.0
                base_8 = 0.0
                iva_8 = 0.0
                exempt_amount = 0.0
                wh_amount = 0.0

                if mc_installed:
                    # Con multicurrency: usar campos VES explícitos del módulo TA
                    total_with_iva = (move.l10n_ve_ta_multicurrency_total_amount or 0.0) * sign
                    for line in move.invoice_line_ids:
                        taxes = get_line_taxes(line.tax_ids)
                        vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                        taxable = getattr(line, 'l10n_ve_ta_multicurrency_taxable_amount', 0.0) or 0.0
                        exempt_amt = getattr(line, 'l10n_ve_ta_multicurrency_exempt_amount', 0.0) or 0.0
                        tax_amt = getattr(line, 'l10n_ve_ta_multicurrency_tax_amount', 0.0) or 0.0
                        if vat_tax:
                            rate = int(round(vat_tax.amount))
                            if rate == 16:
                                base_16 += taxable
                                iva_16 += tax_amt
                            elif rate == 8:
                                base_8 += taxable
                                iva_8 += tax_amt
                        else:
                            exempt_amount += exempt_amt or taxable
                else:
                    # Sin multicurrency: price_subtotal y amount_currency están en la
                    # moneda de la factura (VES cuando la factura se emitió en VES)
                    total_with_iva = move.amount_total * sign
                    for line in move.invoice_line_ids:
                        taxes = get_line_taxes(line.tax_ids)
                        vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                        if vat_tax:
                            rate = int(round(vat_tax.amount))
                            if rate == 16:
                                base_16 += line.price_subtotal
                            elif rate == 8:
                                base_8 += line.price_subtotal
                        else:
                            exempt_amount += line.price_subtotal
                    # IVA desde líneas del asiento en moneda de la factura
                    for line in move.line_ids.filtered(lambda l: l.tax_line_id):
                        tax = line.tax_line_id
                        if 'igtf' in tax.name.lower():
                            continue
                        rate = int(round(tax.amount))
                        if rate == 16:
                            iva_16 += abs(line.amount_currency)
                        elif rate == 8:
                            iva_8 += abs(line.amount_currency)

                base_16 *= sign
                iva_16 *= sign
                base_8 *= sign
                iva_8 *= sign
                exempt_amount *= sign
                taxable_base = base_16 + base_8
                iva_amount = iva_16 + iva_8

            main_number = move.l10n_ve_supplier_invoice_number or move.name
            line_data = {
                'ope': count,
                'date': move.invoice_date,
                'rif': move.partner_id.vat or '',
                'partner_name': move.partner_id.name,
                'is_import': is_import,
                'import_plan': move.ref if is_import else '',
                'import_exp': move.l10n_ve_control_number if is_import else '',
                'doc_number': main_number if doc_type == 'FAC' else '',
                'doc_type': doc_type,
                'control_number': move.l10n_ve_control_number or '',
                'debit_note': main_number if doc_type == 'ND' else '',
                'credit_note': main_number if doc_type == 'NC' else '',
                'tran_type': tran_type,
                'affected_doc': move.reversed_entry_id.l10n_ve_supplier_invoice_number or move.reversed_entry_id.name if move.reversed_entry_id else '',
                'total_with_iva': total_with_iva,
                'exempt_amount': exempt_amount,
                'taxable_base': taxable_base,
                'base_16': base_16,
                'iva_16': iva_16,
                'base_8': base_8,
                'iva_8': iva_8,
                'iva_rate': 16,
                'iva_amount': iva_amount,
                'wh_amount': wh_amount,
                'wh_rate': wh_iva.retention_percentage if wh_iva else 0.0,
                'wh_number': wh_iva.name if wh_iva else '',
                'wh_date': wh_iva.date if wh_iva else False,
            }
            ledger_lines.append(line_data)
            count += 1
            
        return ledger_lines

    def action_generate_pdf(self):
        """
        Genera el Libro de Compras en formato PDF.
        """
        self.ensure_one()
        data = self._get_ledger_data()
        if not data:
            raise UserError(_("No se encontró información"))
            
        report_action = self.env.ref('l10n_ve_simplit_fiscal.action_report_purchase_ledger')
        pdf_content, _report_type = report_action._render_qweb_pdf('l10n_ve_simplit_fiscal.report_purchase_ledger', [self.id])
        
        self.write({
            'state': 'done', 
            'pdf_file': base64.b64encode(pdf_content),
            'pdf_filename': f'Libro_Compras_{self.date_from}_{self.date_to}.pdf'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_generate_excel(self):
        """
        Genera el Libro de Compras en formato Excel.
        """
        self.ensure_one()
        data = self._get_ledger_data()
        if not data:
            raise UserError(_("No se encontró información"))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Libro de Compras')

        # Formatos
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        data_fmt = workbook.add_format({'border': 1, 'align': 'center'})
        num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        total_fmt = workbook.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00', 'bg_color': '#F2F2F2'})

        # Encabezado
        sheet.merge_range('A1:G1', self.company_id.name, title_fmt)
        sheet.write('A2', f'RIF: {self.company_id.vat}')
        sheet.merge_range('H1:R1', 'Libro de Compras I.V.A.', title_fmt)
        sheet.merge_range('H2:R2', f'Desde: {self.date_from} Hasta: {self.date_to}', title_fmt)

        # Cabecera de Tabla
        headers = [
            'Nro Ope', 'Fecha', 'R.I.F.', 'Nombre o razón social', 'Numero Docum.', 'Tipo Doc.', 
            'Numero Control', 'Tipo Tran.', 'Nro. Fac Afectada', 'Total Compras incluyendo IVA', 
            'Compras Exentas', 'Base Imponible', '%', 'Monto IVA', 'Monto Retenido', '% Ret', 
            'Nro. de Comp.', 'Fecha Ret'
        ]
        
        for col, header in enumerate(headers):
            sheet.write(3, col, header, header_fmt)
            sheet.set_column(col, col, 12 if col != 3 else 30)

        # Datos
        row = 4
        totals = {'total': 0.0, 'exempt': 0.0, 'base': 0.0, 'iva': 0.0, 'ret': 0.0}
        
        for l in data:
            sheet.write(row, 0, l['ope'], data_fmt)
            sheet.write(row, 1, str(l['date']), data_fmt)
            sheet.write(row, 2, l['rif'], data_fmt)
            sheet.write(row, 3, l['partner_name'], data_fmt)
            sheet.write(row, 4, l['doc_number'], data_fmt)
            sheet.write(row, 5, l['doc_type'], data_fmt)
            sheet.write(row, 6, l['control_number'], data_fmt)
            sheet.write(row, 7, l['tran_type'], data_fmt)
            sheet.write(row, 8, l['affected_doc'], data_fmt)
            sheet.write(row, 9, l['total_with_iva'], num_fmt)
            sheet.write(row, 10, l['exempt_amount'], num_fmt)
            sheet.write(row, 11, l['taxable_base'], num_fmt)
            sheet.write(row, 12, l['iva_rate'], data_fmt)
            sheet.write(row, 13, l['iva_amount'], num_fmt)
            sheet.write(row, 14, l['wh_amount'], num_fmt)
            sheet.write(row, 15, l['wh_rate'], data_fmt)
            sheet.write(row, 16, l['wh_number'], data_fmt)
            sheet.write(row, 17, str(l['wh_date']) if l['wh_date'] else '', data_fmt)
            
            totals['total'] += l['total_with_iva']
            totals['exempt'] += l['exempt_amount']
            totals['base'] += l['taxable_base']
            totals['iva'] += l['iva_amount']
            totals['ret'] += l['wh_amount']
            row += 1

        # Totales
        sheet.merge_range(row, 0, row, 8, 'TOTALES', workbook.add_format({'bold': True, 'align': 'right', 'border': 1}))
        sheet.write(row, 9, totals['total'], total_fmt)
        sheet.write(row, 10, totals['exempt'], total_fmt)
        sheet.write(row, 11, totals['base'], total_fmt)
        sheet.write(row, 13, totals['iva'], total_fmt)
        sheet.write(row, 14, totals['ret'], total_fmt)

        workbook.close()
        output.seek(0)
        
        self.write({
            'state': 'done',
            'excel_file': base64.b64encode(output.read()),
            'excel_filename': f'Libro_Compras_{self.date_from}_{self.date_to}.xlsx'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
