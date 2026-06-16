# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import logging
import xlsxwriter

_logger = logging.getLogger(__name__)

class AccountIvaSalesLedgerWizard(models.TransientModel):
    _name = 'account.iva.sales.ledger.wizard'
    _description = 'Asistente de Libro de Ventas con IGTF'

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

    report_type = fields.Selection([
        ('daily', 'Libro de Ventas Detallado IGTF'),
        ('detailed', 'Libro de Ventas Detallado')
    ], string='Tipo de Reporte', default='daily', required=True)

    def _get_ledger_data(self):
        """Metodo principal que redirige segun el tipo de reporte"""
        if self.report_type == 'daily':
            return self._get_daily_summary_data()
        else:
            return self._get_detailed_data()

    def _get_daily_summary_data(self):
        """
        Obtiene y procesa los datos para el libro de ventas (Resumen Diario).
        Agrupa por fecha y serial de impresora fiscal.
        """
        self.ensure_one()
        Move = self.env['account.move']
        
        domain = [
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.report_type == 'daily':
            domain.append(('l10n_ve_has_igtf', '=', True))
            
        _logger.info("LIBRO DE VENTAS: Iniciando búsqueda de facturas entre %s y %s", self.date_from, self.date_to)
        moves = Move.search(domain, order='invoice_date asc, l10n_ve_fiscal_printer_serial asc')
        _logger.info("LIBRO DE VENTAS: Facturas encontradas: %s. Empezando procesamiento...", len(moves))
        
        # Agrupamiento por (Fecha, Serial)
        groups = {}
        
        for move in moves:
            date_key = move.invoice_date
            serial = move.l10n_ve_fiscal_printer_serial or 'N/A'
            key = (date_key, serial)
            
            if key not in groups:
                groups[key] = {
                    'date': date_key,
                    'serial': serial,
                    'inv_numbers': [], 
                    'nc_numbers': [],  
                    'z_number': move.l10n_ve_fiscal_z_number or '',
                    'total_with_iva': 0.0,
                    'igtf_base': 0.0,
                    'igtf_amount': 0.0,
                    'exempt_amount': 0.0,
                    'general_base': 0.0,
                    'general_iva': 0.0,
                    'reduced_base': 0.0,
                    'reduced_iva': 0.0,
                }
            
            grp = groups[key]
            sign = -1 if move.move_type == 'out_refund' else 1
            
            num = move.l10n_ve_fiscal_invoice_number or move.name
            if move.move_type == 'out_invoice':
                grp['inv_numbers'].append(num)
            else:
                grp['nc_numbers'].append(num)
                
            mc_installed = 'l10n_ve_ta_multicurrency_total_amount' in move._fields

            if mc_installed:
                grp['total_with_iva'] += (move.l10n_ve_ta_multicurrency_total_amount or 0.0) * sign
            else:
                grp['total_with_iva'] += move.amount_total * sign

            if move.l10n_ve_has_igtf:
                factor = move._get_ves_factor() if hasattr(move, '_get_ves_factor') else 1.0
                grp['igtf_base']   += move.l10n_ve_igtf_base   * factor * sign
                grp['igtf_amount'] += move.l10n_ve_igtf_amount * factor * sign

            def get_line_taxes(tax_ids):
                taxes = []
                for tax in tax_ids:
                    if tax.amount_type == 'group':
                        taxes.extend(get_line_taxes(tax.children_tax_ids))
                    else:
                        taxes.append(tax)
                return taxes

            for line in move.invoice_line_ids:
                taxes = get_line_taxes(line.tax_ids)
                vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)

                if mc_installed:
                    price_subtotal = getattr(line, 'l10n_ve_ta_multicurrency_taxable_amount', 0.0) or 0.0
                    exempt_amt     = getattr(line, 'l10n_ve_ta_multicurrency_exempt_amount', 0.0) or 0.0
                    tax_amt        = getattr(line, 'l10n_ve_ta_multicurrency_tax_amount', 0.0) or 0.0
                else:
                    # price_subtotal está en la moneda de la factura (VES)
                    price_subtotal = line.price_subtotal
                    exempt_amt     = line.price_subtotal
                    tax_amt        = None  # se calcula desde line_ids abajo

                if vat_tax:
                    rate = int(round(vat_tax.amount))
                    if rate == 16:
                        grp['general_base'] += price_subtotal * sign
                        if mc_installed:
                            grp['general_iva'] += tax_amt * sign
                    elif rate == 8:
                        grp['reduced_base'] += price_subtotal * sign
                        if mc_installed:
                            grp['reduced_iva'] += tax_amt * sign
                else:
                    grp['exempt_amount'] += (price_subtotal if mc_installed else exempt_amt) * sign

            if not mc_installed:
                # IVA desde líneas del asiento en moneda de la factura
                for tax_line in move.line_ids.filtered(lambda l: l.display_type == 'tax'):
                    tax_obj = tax_line.tax_line_id
                    if not tax_obj or 'igtf' in tax_obj.name.lower():
                        continue
                    rate = int(round(tax_obj.amount))
                    tax_amount = abs(tax_line.amount_currency) * sign
                    if rate == 16:
                        grp['general_iva'] += tax_amount
                    elif rate == 8:
                        grp['reduced_iva'] += tax_amount

        _logger.info("LIBRO DE VENTAS: Procesamiento de grupos finalizado. Generando respuesta.")
        ledger_lines = []
        count = 1
        sorted_keys = sorted(groups.keys())
        for key in sorted_keys:
            grp = groups[key]
            inv_desde = min(grp['inv_numbers']) if grp['inv_numbers'] else ''
            inv_hasta = max(grp['inv_numbers']) if grp['inv_numbers'] else ''
            nc_desde = min(grp['nc_numbers']) if grp['nc_numbers'] else ''
            nc_hasta = max(grp['nc_numbers']) if grp['nc_numbers'] else ''
            
            line_data = {
                'ope': count,
                'date': grp['date'],
                'serial': grp['serial'],
                'inv_desde': inv_desde,
                'inv_hasta': inv_hasta,
                'nc_desde': nc_desde,
                'nc_hasta': nc_hasta,
                'z_number': grp['z_number'],
                'total_with_iva': grp['total_with_iva'],
                'igtf_base': grp['igtf_base'],
                'igtf_amount': grp['igtf_amount'],
                'exempt_amount': grp['exempt_amount'],
                'general_base': grp['general_base'],
                'general_iva': grp['general_iva'],
                'reduced_base': grp['reduced_base'],
                'reduced_iva': grp['reduced_iva'],
                'additional_base': 0.0,
                'additional_iva': 0.0,
            }
            ledger_lines.append(line_data)
            count += 1
            
        return ledger_lines

    def _get_detailed_data(self):
        """
        Obtiene datos detallados (una linea por factura) para el Libro de Ventas.
        """
        self.ensure_one()
        Move = self.env['account.move']
        domain = [
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.report_type == 'igtf':
            # Solo facturas con IGTF para el reporte "Detallado IGTF"
            domain.append(('l10n_ve_has_igtf', '=', True))
        
        moves = Move.search(domain, order='invoice_date asc, l10n_ve_fiscal_invoice_number asc, name asc')
        
        ledger_lines = []
        count = 1
        for move in moves:
            sign = -1 if move.move_type == 'out_refund' else 1
            is_contribuyente = move.partner_id.vat and len(move.partner_id.vat) > 5 # Simple heuristic
            
            def get_line_taxes(tax_ids):
                taxes = []
                for tax in tax_ids:
                    if tax.amount_type == 'group':
                        taxes.extend(get_line_taxes(tax.children_tax_ids))
                    else:
                        taxes.append(tax)
                return taxes

            # Retenciones IVA ventas
            wh_iva_all = self.env['account.wh.iva'].search([
                ('move_id', '=', move.id),
                ('type', '=', 'sale'),
                ('state', '!=', 'cancel'),
            ])
            wh_iva = wh_iva_all[0] if wh_iva_all else False

            base_16 = 0.0
            iva_16 = 0.0
            base_8 = 0.0
            iva_8 = 0.0
            exempt = 0.0
            iva_retenido = 0.0

            if wh_iva_all:
                # Fuente principal: tablas de retención IVA
                total_c_iva = wh_iva.amount_total_invoice * sign
                exempt = wh_iva.amount_exempt * sign
                for wh in wh_iva_all:
                    aliquot = int(round(wh.tax_aliquot))
                    if aliquot == 16:
                        base_16 += wh.amount_taxable_base * sign
                        iva_16  += wh.amount_vat_tax * sign
                    elif aliquot == 8:
                        base_8 += wh.amount_taxable_base * sign
                        iva_8  += wh.amount_vat_tax * sign
                    iva_retenido += wh.amount_total_ret * sign
            else:
                mc_installed = 'l10n_ve_ta_multicurrency_total_amount' in move._fields
                if mc_installed:
                    total_c_iva = (move.l10n_ve_ta_multicurrency_total_amount or 0.0) * sign
                    for line in move.invoice_line_ids:
                        taxes = get_line_taxes(line.tax_ids)
                        vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                        taxable   = getattr(line, 'l10n_ve_ta_multicurrency_taxable_amount', 0.0) or 0.0
                        exempt_a  = getattr(line, 'l10n_ve_ta_multicurrency_exempt_amount', 0.0) or 0.0
                        tax_amt   = getattr(line, 'l10n_ve_ta_multicurrency_tax_amount', 0.0) or 0.0
                        if vat_tax:
                            rate = int(round(vat_tax.amount))
                            if rate == 16:
                                base_16 += taxable * sign
                                iva_16  += tax_amt * sign
                            elif rate == 8:
                                base_8 += taxable * sign
                                iva_8  += tax_amt * sign
                        else:
                            exempt += (exempt_a or taxable) * sign
                else:
                    total_c_iva = move.amount_total * sign
                    for line in move.invoice_line_ids:
                        taxes = get_line_taxes(line.tax_ids)
                        vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                        if vat_tax:
                            rate = int(round(vat_tax.amount))
                            if rate == 16:
                                base_16 += line.price_subtotal * sign
                            elif rate == 8:
                                base_8 += line.price_subtotal * sign
                        else:
                            exempt += line.price_subtotal * sign
                    for tax_line in move.line_ids.filtered(lambda l: l.display_type == 'tax'):
                        tax_obj = tax_line.tax_line_id
                        if not tax_obj or 'igtf' in tax_obj.name.lower():
                            continue
                        rate = int(round(tax_obj.amount))
                        if rate == 16:
                            iva_16 += abs(tax_line.amount_currency) * sign
                        elif rate == 8:
                            iva_8 += abs(tax_line.amount_currency) * sign

            nro_ret   = wh_iva.name if (wh_iva and wh_iva.name) else ''
            fecha_ret = wh_iva.date.strftime('%d/%m/%Y') if (wh_iva and wh_iva.date) else ''

            # Alícuota dominante del documento
            aliq = 16 if abs(base_16) > 0 else (8 if abs(base_8) > 0 else 0)
            base_total = base_16 + base_8
            iva_total  = iva_16 + iva_8

            # Columnas RETENCIONES (Base e IVA siempre se muestran; Retenido solo si hay wh_iva)
            if wh_iva_all:
                ret_base    = sum(wh.amount_taxable_base for wh in wh_iva_all) * sign
                ret_iva_amt = sum(wh.amount_vat_tax for wh in wh_iva_all) * sign
                ret_pct     = wh_iva.retention_percentage
                percibido   = ret_iva_amt - iva_retenido
            else:
                ret_base    = base_total
                ret_iva_amt = iva_total
                ret_pct     = 0.0
                percibido   = 0.0

            line_data = {
                'ope':            count,
                'date':           move.invoice_date,
                'rif':            move.partner_id.vat or '',
                'name':           move.partner_id.name,
                'doc_type':       'FAC' if move.move_type == 'out_invoice' else 'N/C',
                'tipo_doc':       'FAC' if move.move_type == 'out_invoice' else 'N/C',
                'doc_num':        move.l10n_ve_fiscal_invoice_number or move.name,
                'control_number': move.l10n_ve_control_number or '',
                'serial':         move.l10n_ve_control_number or '',
                'tipo_tran':      '01-REG' if move.move_type == 'out_invoice' else '03-REG',
                'fac_afectada':   move.reversed_entry_id.l10n_ve_fiscal_invoice_number or move.reversed_entry_id.name if move.reversed_entry_id else '',
                'total_c_iva':    total_c_iva,
                'exempt':         exempt,
                # Contribuyentes (alícuota general)
                'base_cnt':  base_total if is_contribuyente else 0.0,
                'aliq_cnt':  aliq       if is_contribuyente else 0,
                'iva_cnt':   iva_total  if is_contribuyente else 0.0,
                'base_contrib': base_total if is_contribuyente else 0.0,
                'iva_contrib':  iva_total if is_contribuyente else 0.0,
                # No contribuyentes (alícuota general)
                'base_ncnt': base_total if not is_contribuyente else 0.0,
                'aliq_ncnt': aliq       if not is_contribuyente else 0,
                'iva_ncnt':  iva_total  if not is_contribuyente else 0.0,
                'base_no_contrib': base_total if not is_contribuyente else 0.0,
                'iva_no_contrib':  iva_total if not is_contribuyente else 0.0,
                # Retenciones
                'ret_base':     ret_base,
                'ret_iva':      ret_iva_amt,
                'ret_retenido': iva_retenido,
                'iva_retenido': iva_retenido,
                'ret_pct':      ret_pct,
                'percibido':    percibido,
                'nro_ret':      nro_ret,
                'fecha_ret':    fecha_ret,
            }
            ledger_lines.append(line_data)
            count += 1
            
        return ledger_lines

    def action_generate_pdf(self):
        self.ensure_one()
        data = self._get_ledger_data()
        if not data:
            raise UserError(_("No se encontró información"))
            
        if self.report_type == 'detailed':
            report_xml_id = 'l10n_ve_simplit_fiscal.action_report_sales_ledger_detailed'
            filename = f'Libro_Ventas_Detallado_{self.date_from}_{self.date_to}.pdf'
            template_id = 'l10n_ve_simplit_fiscal.report_sales_ledger_detailed'
        else:
            report_xml_id = 'l10n_ve_simplit_fiscal.action_report_sales_ledger_igtf'
            filename = f'Libro_Ventas_IGTF_{self.date_from}_{self.date_to}.pdf'
            template_id = 'l10n_ve_simplit_fiscal.report_sales_ledger_igtf'

        report_action = self.env.ref(report_xml_id)
        _logger.info("LIBRO DE VENTAS: Iniciando renderizado PDF qweb...")
        # Odoo 18: _render_qweb_pdf requires report_ref (template_id) as first argument
        pdf_content, report_type = report_action._render_qweb_pdf(template_id, res_ids=[self.id])
        _logger.info("LIBRO DE VENTAS: Renderizado PDF finalizado.")

        self.write({
            'state': 'done', 
            'pdf_file': base64.b64encode(pdf_content),
            'pdf_filename': filename
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_generate_excel(self):
        self.ensure_one()
        data = self._get_ledger_data()
        if not data:
            raise UserError(_("No se encontró información"))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Libro de Ventas IGTF')

        # Formatos
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        data_fmt = workbook.add_format({'border': 1, 'align': 'center'})
        num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        total_fmt = workbook.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00', 'bg_color': '#F2F2F2'})

        # Header
        sheet.merge_range('A1:G1', self.company_id.name, title_fmt)
        sheet.write('A2', f'RIF: {self.company_id.vat}')
        
        report_title = 'Libro de Ventas Con IGTF (Resumen Diario)' if self.report_type == 'daily' else 'Libro de Ventas Con IGTF (Detallado)'
        sheet.merge_range('H1:P1', report_title, title_fmt)

        if self.report_type == 'daily':
            headers = [
                'Fecha', 'Razon Social', 'Serial', 'Fact. Desde', 'Fact. Hasta', 'NC Desde', 'NC Hasta',
                'N° Z', 'Total c/IVA', 'IGTF Base', '% IGTF', 'Monto IGTF', 'Exento', 'General Base',
                '% IVA', 'Monto IVA', 'Reducida Base', 'Reducida IVA', 'Adicional Base', 'Adicional IVA'
            ]
        else:
            headers = [
                'Nro Ope', 'Fecha', 'ID Fiscal', 'Nombre o razón social', 'Tipo', 'Serial', 'Numero', 'Tran', 'Fact. Afectada',
                'Total c/IVA', 'Exento', 'Base Contrib.', 'IVA Contrib.', 'Base No Contrib.', 'IVA No Contrib.',
                'IVA Retenido', 'Comprobante', 'Fecha Comp.'
            ]
        
        for col, header in enumerate(headers):
            sheet.write(3, col, header, header_fmt)
            # Ajustar anchos basicos
            sheet.set_column(col, col, 12 if col != 3 else 30)

        row = 4
        for l in data:
            if self.report_type == 'daily':
                sheet.write(row, 0, str(l['date']), data_fmt)
                sheet.write(row, 1, 'RESUMEN DIARIO', data_fmt)
                sheet.write(row, 2, l['serial'], data_fmt)
                sheet.write(row, 3, l['inv_desde'], data_fmt)
                sheet.write(row, 4, l['inv_hasta'], data_fmt)
                sheet.write(row, 5, l['nc_desde'], data_fmt)
                sheet.write(row, 6, l['nc_hasta'], data_fmt)
                sheet.write(row, 7, l['z_number'], data_fmt)
                sheet.write(row, 8, l['total_with_iva'], num_fmt)
                sheet.write(row, 9, l['igtf_base'], num_fmt)
                sheet.write(row, 10, 3.0 if l['igtf_amount'] else 0.0, data_fmt)
                sheet.write(row, 11, l['igtf_amount'], num_fmt)
                sheet.write(row, 12, l['exempt_amount'], num_fmt)
                sheet.write(row, 13, l['general_base'], num_fmt)
                sheet.write(row, 14, 16.0 if l['general_iva'] else 0.0, data_fmt)
                sheet.write(row, 15, l['general_iva'], num_fmt)
                sheet.write(row, 16, 0.0, num_fmt)
                sheet.write(row, 17, 0.0, num_fmt)
                sheet.write(row, 18, 0.0, num_fmt)
                sheet.write(row, 19, 0.0, num_fmt)
            else:
                sheet.write(row, 0, l['ope'], data_fmt)
                sheet.write(row, 1, str(l['date']), data_fmt)
                sheet.write(row, 2, l['rif'], data_fmt)
                sheet.write(row, 3, l['name'], data_fmt)
                sheet.write(row, 4, l['tipo_doc'], data_fmt)
                sheet.write(row, 5, l['serial'], data_fmt)
                sheet.write(row, 6, l['doc_num'], data_fmt)
                sheet.write(row, 7, l['tipo_tran'], data_fmt)
                sheet.write(row, 8, l['fac_afectada'], data_fmt)
                sheet.write(row, 9, l['total_c_iva'], num_fmt)
                sheet.write(row, 10, l['exempt'], num_fmt)
                sheet.write(row, 11, l['base_contrib'], num_fmt)
                sheet.write(row, 12, l['iva_contrib'], num_fmt)
                sheet.write(row, 13, l['base_no_contrib'], num_fmt)
                sheet.write(row, 14, l['iva_no_contrib'], num_fmt)
                sheet.write(row, 15, l['iva_retenido'], num_fmt)
                sheet.write(row, 16, l['nro_ret'], data_fmt)
                sheet.write(row, 17, l['fecha_ret'], data_fmt)
            row += 1

        workbook.close()
        output.seek(0)
        
        self.write({
            'state': 'done',
            'excel_file': base64.b64encode(output.read()),
            'excel_filename': f'Libro_Ventas_IGTF_{self.date_from}_{self.date_to}.xlsx'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
