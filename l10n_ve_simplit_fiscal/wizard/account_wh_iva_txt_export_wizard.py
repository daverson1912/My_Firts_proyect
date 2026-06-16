# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import json
import requests
import base64
import logging

from ..models.utils import get_api_url

_logger = logging.getLogger(__name__)

class AccountWhIvaTxtExportWizard(models.TransientModel):
    _name = 'account.wh.iva.txt.export.wizard'
    _description = 'Asistente para Exportar TXT de IVA (SENIAT)'

    wh_iva_ids = fields.Many2many(
        comodel_name='account.wh.iva',
        string='Comprobantes de Retención',
        required=True,
    )

    state = fields.Selection([
        ('draft', 'Selección'),
        ('done', 'Generado')
    ], string='Estado', default='draft')

    txt_filename = fields.Char(string='Archivo TXT')
    txt_file = fields.Binary(string='Contenido TXT', attachment=True)
    
    # Campo para la confirmación de "Declarado"
    mark_as_declared = fields.Boolean(
        string='¿Desea colocar estas retenciones como declaradas ante el SENIAT?',
        default=False
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get('active_model') == 'account.wh.iva' and self._context.get('active_ids'):
            ids = self._context.get('active_ids')
            recs = self.env['account.wh.iva'].browse(ids).filtered(lambda r: r.state != 'declared' and r.type == 'purchase')
            if not recs:
                raise UserError(_("No hay comprobantes válidos para exportar (los seleccionados ya están declarados o no son válidos)."))
            res['wh_iva_ids'] = [(6, 0, recs.ids)]
        elif self._context.get('active_model') == 'account.wh.iva.summary' and self._context.get('active_ids'):
            # Si vienen del resumen, cargamos todos los hijos asociados que no estén declarados
            summaries = self.env['account.wh.iva.summary'].browse(self._context.get('active_ids'))
            all_ids = []
            for s in summaries:
                all_ids.extend(s.line_ids.filtered(lambda r: r.state != 'declared' and r.type == 'purchase').ids)
            if not all_ids:
                raise UserError(_("No hay comprobantes válidos para exportar en los resúmenes seleccionados."))
            res['wh_iva_ids'] = [(6, 0, all_ids)]
        return res

    def action_generate_txt(self):
        self.ensure_one()
        
        # 1. Preparar datos para el API
        items = []
        # Validar que ninguno esté declarado antes de procesar
        declared_recs = self.wh_iva_ids.filtered(lambda r: r.state == 'declared')
        if declared_recs:
            unique_names = sorted(list(set(declared_recs.mapped('name'))))
            names = ", ".join(unique_names)
            raise UserError(_("No se puede generar el archivo TXT porque los siguientes comprobantes ya han sido declarados ante el SENIAT: %s") % names)

        for wh in self.wh_iva_ids:
            # Validaciones básicas de integridad
            if not wh.name:
                raise UserError(_("El comprobante de la factura %s no tiene número asignado.") % wh.invoice_number)
            
            # Formateo de Periodo (Periodo: YYYYMM)
            period = wh.date.strftime('%Y%m')
            
            # Tipo de Operación: C (Compra), V (Venta)? El API pide C
            # Tipo de Documento: 01 (Factura), 02 (Debito), 03 (Credito)
            doc_type = '01'
            if wh.wh_type == 'refund':
                doc_type = '03'
            
            # Montos
            # totalAmount: Monto total con IVA
            # taxBase: Base imponible
            # withheldAmount: Monto retenido
            # exemptAmount: Monto exento
            
            # RIFs
            agent_rif = (wh.company_id.vat or wh.company_id.partner_id.vat or '').replace('-', '').strip()
            supplier_rif = (wh.partner_id.vat or '').replace('-', '').strip()

            if not agent_rif:
                raise UserError(_("La compañía %s no tiene un RIF configurado.") % wh.company_id.name)
            if not supplier_rif:
                raise UserError(_("El proveedor %s no tiene un RIF configurado.") % wh.partner_id.name)

            item = {
                "agentFiscalId": agent_rif,
                "period": period,
                "invoiceDate": wh.invoice_date.strftime('%Y-%m-%d'),
                "operationType": "C", # Hardcoded a Compras dado que estamos en retenciones de proveedor
                "documentType": doc_type,
                "supplierFiscalId": supplier_rif,
                "invoiceNumber": wh.supplier_invoice_number or wh.invoice_number,
                "controlNumber": wh.control_number or '0',
                "totalAmount": float(wh.amount_total_invoice),
                "taxBase": float(wh.amount_taxable_base),
                "withheldAmount": float(wh.amount_total_ret),
                "affectedDocumentNumber": wh.affected_invoice_number or "0",
                "voucherNumber": wh.name,
                "exemptAmount": float(wh.amount_exempt),
                "taxRate": int(wh.tax_aliquot),
                "caseNumber": "0"
            }
            items.append(item)

        payload = {"items": items}
        _logger.info(f"[FISCAL] Payload TXT IVA: {json.dumps(payload)}")
        
        # 2. Llamada al API
        api_host = get_api_url()
        if not api_host:
            raise UserError(_("No se ha configurado la URL del API de Simplit Fiscal (revise el archivo globalConfig.json)."))
        
        url = f"{api_host.rstrip('/')}/api/v1/fiscal-reports/iva-txt"
        
        # Obtener API Key de la configuración fiscal para la compañía del primer comprobante
        api_key = False
        if self.wh_iva_ids:
            company = self.wh_iva_ids[0].company_id
            config = self.env['simplitfiscal.config'].search([('company_id', '=', company.id)], limit=1)
            api_key = config.ta_api_key if config else False

        headers = {}
        if api_key:
            headers['X-API-Key'] = api_key

        try:
            _logger.info(f"[FISCAL] Enviando datos a API para TXT IVA: {url}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            _logger.info(f"[FISCAL] Response Body: {response.text}")
            
            try:
                res_data = response.json()
            except:
                res_data = {}

            # 1. Validar Status HTTP
            if response.status_code not in (200, 201):
                msg = res_data.get('message') or _("Error de comunicación con el Servicio Fiscal (Status: %s).") % response.status_code
                raise UserError(msg)

            # 2. Validar campo error (si es JSON)
            if res_data and res_data.get('error', 0) != 0:
                msg = res_data.get('message', _("Error desconocido en el Servicio Fiscal."))
                raise UserError(msg)

            # 3. Obtener contenido (puede ser directo o en campo 'data' según versión)
            if res_data and 'data' in res_data:
                content_raw = res_data['data']
                # Si viene como string base64
                if isinstance(content_raw, str):
                    try:
                        content = base64.b64decode(content_raw)
                    except:
                        content = content_raw.encode('utf-8')
                else:
                    content = str(content_raw).encode('utf-8')
            else:
                content = response.content
            
            if not content:
                raise UserError(_("El Servicio Fiscal no devolvió ningún contenido para el archivo TXT."))

            # Codificar a base64 para guardarlo en Odoo
            self.write({
                'txt_file': base64.b64encode(content),
                'txt_filename': f"IVA_RET_{period}.txt",
                'state': 'done'
            })
            
        except Exception as e:
            if isinstance(e, UserError):
                raise e
            _logger.error(f"[FISCAL] Error al llamar al API TXT: {str(e)}")
            raise UserError(_("No se pudo generar el archivo TXT. Por favor contacte con soporte técnico."))

        # Mantener el wizard abierto para la descarga y confirmación
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_declared(self):
        self.ensure_one()
        if self.mark_as_declared:
            self.wh_iva_ids.action_mark_as_declared()
        return {'type': 'ir.actions.act_window_close'}
