# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging

_logger = logging.getLogger(__name__)

class AccountIgtfReportWizard(models.TransientModel):
    _name = 'account.igtf.report.wizard'
    _description = 'Asistente de Reporte de IGTF General'

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
    
    # Campo para la descarga del archivo generado
    pdf_file = fields.Binary(string='Archivo PDF', readonly=True)
    pdf_filename = fields.Char(string='Nombre PDF', readonly=True)
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Generado')
    ], string='Estado', default='draft')

    def _get_igtf_data(self):
        """
        Obtiene y procesa los datos para el reporte de IGTF.
        Agrupa por fecha y calcula totales por Facturas y Notas de Crédito.
        """
        self.ensure_one()
        Move = self.env['account.move']
        
        domain = [
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('l10n_ve_has_igtf', '=', True),
        ]
        
        moves = Move.search(domain, order='invoice_date asc')
        
        # Agrupamiento por fecha
        daily_data = {}
        
        # Totales por concepto para el resumen inferior
        summary = {
            'out_invoice': {'count': 0, 'base': 0.0, 'igtf': 0.0},
            'out_refund': {'count': 0, 'base': 0.0, 'igtf': 0.0},
        }
        
        for move in moves:
            date_str = move.invoice_date.strftime('%d/%m/%Y')
            if date_str not in daily_data:
                daily_data[date_str] = {
                    'date': move.invoice_date,
                    'n_facturas': 0,
                    'n_notas_c': 0,
                    'venta_total': 0.0,
                    'base': 0.0,
                    'percentage': move.l10n_ve_igtf_percentage,
                    'igtf': 0.0,
                }
            
            # Determinar impacto según tipo
            sign = 1
            if move.move_type == 'out_refund':
                daily_data[date_str]['n_notas_c'] += 1
                sign = -1
                summary['out_refund']['count'] += 1
                summary['out_refund']['base'] += move.l10n_ve_igtf_base
            else:
                daily_data[date_str]['n_facturas'] += 1
                summary['out_invoice']['count'] += 1
                summary['out_invoice']['base'] += move.l10n_ve_igtf_base

            # El IGTF ya está guardado en l10n_ve_igtf_amount
            igtf_move = move.l10n_ve_igtf_amount
            
            if move.move_type == 'out_refund':
                summary['out_refund']['igtf'] += igtf_move
            else:
                summary['out_invoice']['igtf'] += igtf_move

            # Acumular en el día (firmado para totales correctos)
            daily_data[date_str]['venta_total'] += move.amount_total * sign
            daily_data[date_str]['base'] += move.l10n_ve_igtf_base * sign
            daily_data[date_str]['igtf'] += igtf_move * sign

        # Convertir diccionario a lista ordenada por fecha
        sorted_lines = sorted(daily_data.values(), key=lambda x: x['date'])
        
        return {
            'lines': sorted_lines,
            'summary': summary,
            'total_general': {
                'venta_total': sum(l['venta_total'] for l in sorted_lines),
                'base': sum(l['base'] for l in sorted_lines),
                'igtf': sum(l['igtf'] for l in sorted_lines),
                'transactions': summary['out_invoice']['count'] + summary['out_refund']['count'],
            }
        }

    def action_generate_pdf(self):
        """
        Genera el Reporte de IGTF en formato PDF.
        """
        self.ensure_one()
        data = self._get_igtf_data()
        if not data['lines']:
            raise UserError(_("No se encontró información de IGTF para el período seleccionado."))
            
        report_action = self.env.ref('l10n_ve_simplit_fiscal.action_report_igtf_general')
        pdf_content, _report_type = report_action._render_qweb_pdf('l10n_ve_simplit_fiscal.report_igtf_general', [self.id])
        
        self.write({
            'state': 'done', 
            'pdf_file': base64.b64encode(pdf_content),
            'pdf_filename': f'Reporte_IGTF_{self.date_from}_{self.date_to}.pdf'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
