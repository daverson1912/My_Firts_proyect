# -*- coding: utf-8 -*-

from odoo import models, api, _



class AccountIvaPurchaseLedgerWizard(models.TransientModel):

    _inherit = 'account.iva.purchase.ledger.wizard'



    def _get_ledger_data(self):

        """

        Extensión para el Libro de Compras: Si la integración fiscal multimoneda 

        está activa, utiliza los campos calculados en Bolívares (VES).

        """

        config = self.env['l10n_ve_ta_multicurrency.api.config'].search([

            ('company_id', '=', self.company_id.id)

        ], limit=1)

        

        if not config or not config.l10n_ve_ta_multicurrency_enable_fiscal:

            return super(AccountIvaPurchaseLedgerWizard, self)._get_ledger_data()



        # Lógica duplicada de l10n_ve_simplit_fiscal pero usando campos Ref. (VES)

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

            doc_type = 'NC' if move.move_type == 'in_refund' else 'FAC'

            if getattr(move, 'debit_origin_id', False): doc_type = 'ND'

            

            tran_type = '03-ANUL' if (move.payment_state == 'reversed' or (move.amount_total == 0 and move.state == 'cancel')) else '01-REG'

            

            wh_iva = self.env['account.wh.iva'].search([

                ('move_id', '=', move.id),

                ('state', '!=', 'cancel')

            ], limit=1)

            

            sign = -1 if move.move_type == 'in_refund' else 1
            
            # USAR CAMPOS EN BOLIVARES (VES) - DIVISION POR TASA (16% Y 8%)
            total_with_iva = move.l10n_ve_ta_multicurrency_total_amount * sign
            wh_amount = (wh_iva.l10n_ve_ta_multicurrency_amount_total_ret if wh_iva else 0.0) * sign
            wh_rate = wh_iva.retention_percentage if wh_iva else 0.0

            base_16 = 0.0
            iva_16 = 0.0
            base_8 = 0.0
            iva_8 = 0.0
            exempt_amount = 0.0
            
            for line in move.invoice_line_ids:
                taxes = []
                for tax in line.tax_ids:
                    if tax.amount_type == 'group':
                        taxes.extend(tax.children_tax_ids)
                    else:
                        taxes.append(tax)
                
                vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                taxable = getattr(line, 'l10n_ve_ta_multicurrency_taxable_amount', 0.0)
                exempt_amt = getattr(line, 'l10n_ve_ta_multicurrency_exempt_amount', 0.0)
                tax_amt = getattr(line, 'l10n_ve_ta_multicurrency_tax_amount', 0.0)
                
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
                    
            base_16 = base_16 * sign
            iva_16 = iva_16 * sign
            base_8 = base_8 * sign
            iva_8 = iva_8 * sign
            exempt_amount = exempt_amount * sign
            taxable_base = (base_16 + base_8)
            iva_amount = (iva_16 + iva_8)

            is_import = bool(move.partner_id.country_id and move.partner_id.country_id.code != 'VE')
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
                'wh_rate': wh_rate,
                'wh_number': wh_iva.name if wh_iva else '',
                'wh_date': wh_iva.date if wh_iva else False,
            }

            ledger_lines.append(line_data)

            count += 1

            

        return ledger_lines





class AccountIvaSalesLedgerWizard(models.TransientModel):

    _inherit = 'account.iva.sales.ledger.wizard'



    def _get_detailed_data(self):

        """

        Extensión para el Libro de Ventas Detallado: Usa campos en Bolívares (VES).

        """

        config = self.env['l10n_ve_ta_multicurrency.api.config'].search([

            ('company_id', '=', self.company_id.id)

        ], limit=1)

        

        if not config or not config.l10n_ve_ta_multicurrency_enable_fiscal:

            return super(AccountIvaSalesLedgerWizard, self)._get_detailed_data()



        self.ensure_one()

        Move = self.env['account.move']

        domain = [

            ('move_type', 'in', ('out_invoice', 'out_refund')),

            ('state', '=', 'posted'),

            ('invoice_date', '>=', self.date_from),

            ('invoice_date', '<=', self.date_to),

            ('company_id', '=', self.company_id.id),

        ]

        moves = Move.search(domain, order='invoice_date asc, l10n_ve_fiscal_invoice_number asc, name asc')

        

        ledger_lines = []

        count = 1

        for move in moves:

            sign = -1 if move.move_type == 'out_refund' else 1

            is_contribuyente = move.partner_id.vat and len(move.partner_id.vat) > 5

            

            # USAR CAMPOS EN BOLIVARES (VES) - DIVISION POR TASA (16% Y 8%)
            total_c_iva = move.l10n_ve_ta_multicurrency_total_amount * sign
            wh_iva = self.env['account.wh.iva'].search([
                ('move_id', '=', move.id),
                ('state', '!=', 'cancel')
            ], limit=1)
            iva_retenido = (wh_iva.l10n_ve_ta_multicurrency_amount_total_ret if wh_iva else 0.0) * sign
            
            base_16 = 0.0
            iva_16 = 0.0
            base_8 = 0.0
            iva_8 = 0.0
            exempt = 0.0
            
            for line in move.invoice_line_ids:
                taxes = []
                for tax in line.tax_ids:
                    if tax.amount_type == 'group':
                        taxes.extend(tax.children_tax_ids)
                    else:
                        taxes.append(tax)
                
                vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                taxable = getattr(line, 'l10n_ve_ta_multicurrency_taxable_amount', 0.0)
                exempt_amt = getattr(line, 'l10n_ve_ta_multicurrency_exempt_amount', 0.0)
                tax_amt = getattr(line, 'l10n_ve_ta_multicurrency_tax_amount', 0.0)
                
                if vat_tax:
                    rate = int(round(vat_tax.amount))
                    if rate == 16:
                        base_16 += taxable
                        iva_16 += tax_amt
                    elif rate == 8:
                        base_8 += taxable
                        iva_8 += tax_amt
                else:
                    exempt += exempt_amt or taxable
                    
            base_16 = base_16 * sign
            iva_16 = iva_16 * sign
            base_8 = base_8 * sign
            iva_8 = iva_8 * sign
            exempt = exempt * sign

            if is_contribuyente:
                base_g_cnt = base_16
                iva_g_cnt = iva_16
                base_r_cnt = base_8
                iva_r_cnt = iva_8
                base_g_ncnt = 0.0
                iva_g_ncnt = 0.0
                base_r_ncnt = 0.0
                iva_r_ncnt = 0.0
            else:
                base_g_cnt = 0.0
                iva_g_cnt = 0.0
                base_r_cnt = 0.0
                iva_r_cnt = 0.0
                base_g_ncnt = base_16
                iva_g_ncnt = iva_16
                base_r_ncnt = base_8
                iva_r_ncnt = iva_8

            line_data = {
                'ope': count,
                'date': move.invoice_date,
                'rif': move.partner_id.vat or 'N/A',
                'name': move.partner_id.name,
                'tipo_doc': '01-REG' if move.move_type == 'out_invoice' else '03-NC',
                'serial': move.l10n_ve_fiscal_printer_serial or 'N/A',
                'doc_num': move.l10n_ve_fiscal_invoice_number or move.name,
                'tipo_tran': '01-REG' if move.move_type == 'out_invoice' else '03-REG',
                'fac_afectada': move.reversed_entry_id.l10n_ve_fiscal_invoice_number or move.reversed_entry_id.name if move.reversed_entry_id else '',
                'total_c_iva': total_c_iva,
                'exempt': exempt,
                # Contribuyentes vs No Contribuyentes
                'base_contrib': base_g_cnt,
                'iva_contrib': iva_g_cnt,
                'base_no_contrib': base_g_ncnt,
                'iva_no_contrib': iva_g_ncnt,
                # Campos adicionales divididos
                'base_g_cnt': base_g_cnt,
                'iva_g_cnt': iva_g_cnt,
                'base_r_cnt': base_r_cnt,
                'iva_r_cnt': iva_r_cnt,
                'base_g_ncnt': base_g_ncnt,
                'iva_g_ncnt': iva_g_ncnt,
                'base_r_ncnt': base_r_ncnt,
                'iva_r_ncnt': iva_r_ncnt,
                'iva_retenido': iva_retenido,
                'nro_ret': wh_iva.name if wh_iva else '',
                'fecha_ret': wh_iva.date if wh_iva else '',
                'percibido': 0.0,
            }

            ledger_lines.append(line_data)

            count += 1

            

        return ledger_lines



    def _get_daily_summary_data(self):

        """

        Extensión para el Libro de Ventas (Resumen Diario): Usa campos en Bolívares (VES).

        """

        config = self.env['l10n_ve_ta_multicurrency.api.config'].search([

            ('company_id', '=', self.company_id.id)

        ], limit=1)

        

        if not config or not config.l10n_ve_ta_multicurrency_enable_fiscal:

            return super(AccountIvaSalesLedgerWizard, self)._get_daily_summary_data()



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

            

        moves = Move.search(domain, order='invoice_date asc, l10n_ve_fiscal_printer_serial asc')

        

        groups = {}

        for move in moves:

            date_key = move.invoice_date

            serial = move.l10n_ve_fiscal_printer_serial or 'N/A'

            key = (date_key, serial)

            

            if key not in groups:
                groups[key] = {
                    'date': date_key, 'serial': serial, 'inv_numbers': [], 'nc_numbers': [],
                    'z_number': move.l10n_ve_fiscal_z_number or '',
                    'total_with_iva': 0.0, 'igtf_base': 0.0, 'igtf_amount': 0.0,
                    'exempt_amount': 0.0, 'general_base': 0.0, 'general_iva': 0.0,
                    'reduced_base': 0.0, 'reduced_iva': 0.0,
                }
            
            grp = groups[key]
            sign = -1 if move.move_type == 'out_refund' else 1
            
            num = move.l10n_ve_fiscal_invoice_number or move.name
            if move.move_type == 'out_invoice': grp['inv_numbers'].append(num)
            else: grp['nc_numbers'].append(num)
                
            # USAR CAMPOS EN BOLIVARES (VES) - DIVISION POR TASA (16% Y 8%)
            base_16 = 0.0
            iva_16 = 0.0
            base_8 = 0.0
            iva_8 = 0.0
            exempt = 0.0
            
            for line in move.invoice_line_ids:
                taxes = []
                for tax in line.tax_ids:
                    if tax.amount_type == 'group':
                        taxes.extend(tax.children_tax_ids)
                    else:
                        taxes.append(tax)
                
                vat_tax = next((t for t in taxes if t.amount > 0 and 'igtf' not in t.name.lower()), None)
                taxable = getattr(line, 'l10n_ve_ta_multicurrency_taxable_amount', 0.0)
                exempt_amt = getattr(line, 'l10n_ve_ta_multicurrency_exempt_amount', 0.0)
                tax_amt = getattr(line, 'l10n_ve_ta_multicurrency_tax_amount', 0.0)
                
                if vat_tax:
                    rate = int(round(vat_tax.amount))
                    if rate == 16:
                        base_16 += taxable
                        iva_16 += tax_amt
                    elif rate == 8:
                        base_8 += taxable
                        iva_8 += tax_amt
                else:
                    exempt += exempt_amt or taxable

            grp['total_with_iva'] += move.l10n_ve_ta_multicurrency_total_amount * sign
            grp['general_base'] += base_16 * sign
            grp['general_iva'] += iva_16 * sign
            grp['reduced_base'] += base_8 * sign
            grp['reduced_iva'] += iva_8 * sign
            grp['exempt_amount'] += exempt * sign
            
            if move.l10n_ve_has_igtf:
                # El IGTF también debe convertirse a VES si la factura está en USD
                factor = move._get_l10n_ve_ta_multicurrency_factor()
                grp['igtf_base'] += move.l10n_ve_igtf_base * factor * sign
                grp['igtf_amount'] += move.l10n_ve_igtf_amount * factor * sign

        ledger_lines = []
        count = 1
        sorted_keys = sorted(groups.keys())
        for key in sorted_keys:
            grp = groups[key]
            line_data = {
                'ope': count, 'date': grp['date'], 'serial': grp['serial'],
                'inv_desde': min(grp['inv_numbers']) if grp['inv_numbers'] else '',
                'inv_hasta': max(grp['inv_numbers']) if grp['inv_numbers'] else '',
                'nc_desde': min(grp['nc_numbers']) if grp['nc_numbers'] else '',
                'nc_hasta': max(grp['nc_numbers']) if grp['nc_numbers'] else '',
                'z_number': grp['z_number'],
                'total_with_iva': grp['total_with_iva'],
                'igtf_base': grp['igtf_base'], 'igtf_amount': grp['igtf_amount'],
                'exempt_amount': grp['exempt_amount'], 'general_base': grp['general_base'],
                'general_iva': grp['general_iva'],
                'reduced_base': grp['reduced_base'], 'reduced_iva': grp['reduced_iva'], 'additional_base': 0.0, 'additional_iva': 0.0,
            }
            ledger_lines.append(line_data)
            count += 1
        return ledger_lines

