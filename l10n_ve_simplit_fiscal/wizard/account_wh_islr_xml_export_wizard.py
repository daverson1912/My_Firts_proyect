# -*- coding: utf-8 -*-

import json
import requests
import logging
import base64
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..models.utils import get_api_url

_logger = logging.getLogger(__name__)

class AccountWhIslrXmlExportWizard(models.TransientModel):
    _name = 'account.wh.islr.xml.export.wizard'
    _description = 'Asistente de Exportación XML ISLR'

    wh_islr_ids = fields.Many2many(
        comodel_name='account.wh.islr',
        string='Comprobantes de ISLR',
    )
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )

    xml_file = fields.Binary(string='Archivo XML', readonly=True)
    xml_filename = fields.Char(string='Nombre del Archivo XML')
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Generado')
    ], string='Estado', default='draft')

    mark_as_declared = fields.Boolean(
        string='Marcar como declaradas al confirmar', 
        default=True,
        help='Si se marca, al confirmar el asistente las retenciones pasarán a estado "Declarado".'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get('active_model') == 'account.wh.islr' and self._context.get('active_ids'):
            ids = self._context.get('active_ids')
            recs = self.env['account.wh.islr'].browse(ids).filtered(lambda r: r.state != 'declared' and r.type == 'purchase')
            if not recs:
                raise UserError(_("No hay comprobantes válidos para exportar (los seleccionados ya están declarados o no son válidos)."))
            
            # Validar que todos sean de la misma compañía
            if len(recs.mapped('company_id')) > 1:
                raise UserError(_("Solo puede exportar comprobantes de una misma compañía a la vez."))
                
            res['wh_islr_ids'] = [(6, 0, recs.ids)]
            res['company_id'] = recs[0].company_id.id
            
        elif self._context.get('active_model') == 'account.wh.islr.summary' and self._context.get('active_ids'):
            summaries = self.env['account.wh.islr.summary'].browse(self._context.get('active_ids'))
            all_ids = []
            for s in summaries:
                all_ids.extend(s.line_ids.filtered(lambda r: r.state != 'declared' and r.type == 'purchase').ids)
            
            if not all_ids:
                raise UserError(_("No hay comprobantes válidos para exportar en los resúmenes seleccionados."))
            
            recs = self.env['account.wh.islr'].browse(all_ids)
            if len(recs.mapped('company_id')) > 1:
                raise UserError(_("Solo puede exportar comprobantes de una misma compañía a la vez."))
                
            res['wh_islr_ids'] = [(6, 0, all_ids)]
            res['company_id'] = recs[0].company_id.id
            
        return res

    def action_generate_xml(self):
        """
        Llama al API para generar el archivo XML de ISLR.
        """
        # 1. Preparar datos para el API
        items = []
        
        # Validar que ninguno esté declarado antes de procesar
        declared_recs = self.wh_islr_ids.filtered(lambda r: r.state == 'declared')
        if declared_recs:
            unique_names = sorted(list(set(declared_recs.mapped('name') or declared_recs.mapped('invoice_number'))))
            names = ", ".join(unique_names)
            raise UserError(_("No se puede generar el archivo XML porque los siguientes comprobantes ya han sido declarados ante el SENIAT: %s") % names)

        # Validar compañía única (doble chequeo)
        if len(self.wh_islr_ids.mapped('company_id')) > 1:
            raise UserError(_("Solo puede exportar comprobantes de una misma compañía."))

        agent_rif = self.company_id.vat
        if not agent_rif:
            raise UserError(_("La compañía seleccionada no tiene RIF configurado."))

        agent_rif_clean = agent_rif.replace("-", "").strip()
        first_date = self.wh_islr_ids[0].date
        period = first_date.strftime('%Y%m')

        if not self.wh_islr_ids:
            raise UserError(_("No se han seleccionado comprobantes para exportar."))

        for wh in self.wh_islr_ids:
            if not wh.partner_id.vat:
                raise UserError(_("El proveedor %s no tiene RIF configurado.") % wh.partner_id.name)
            
            supplier_rif = wh.partner_id.vat.replace("-", "").strip()
            
            # Cargamos líneas de detalle (usando search manual como fallback por robustez)
            line_records = wh.line_ids
            if not line_records:
                line_records = self.env['account.wh.islr.line'].search([('islr_id', '=', wh.id)])

            for line in line_records:
                items.append({
                    "supplierFiscalId": supplier_rif,
                    "invoiceNumber": wh.move_id.l10n_ve_supplier_invoice_number or "",
                    "controlNumber": wh.move_id.l10n_ve_control_number or "",
                    "operationDate": wh.date.strftime('%d/%m/%Y'),
                    "conceptCode": line.fiscal_code or "",
                    "operationAmount": float(line.base_amount),
                    "retentionPercentage": float(line.retention_percentage)
                })

        payload = {
            "agentFiscalId": agent_rif_clean,
            "period": period,
            "items": items
        }

        # 2. Llamada al API
        api_host = get_api_url()
        if not api_host:
            raise UserError(_("No se ha configurado la URL del API de Simplit Fiscal (revise el archivo globalConfig.json)."))
        
        url = f"{api_host.rstrip('/')}/api/v1/fiscal-reports/islr-xml"
        
        # Obtener API Key de la configuración fiscal para la compañía seleccionada
        config = self.env['simplitfiscal.config'].search([('company_id', '=', self.company_id.id)], limit=1)
        api_key = config.ta_api_key if config else False

        headers = {}
        if api_key:
            headers['X-API-Key'] = api_key

        try:
            _logger.info(f"[FISCAL-ISLR] Enviando datos a API para XML ISLR: {url}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            _logger.info(f"[FISCAL-ISLR] Response Body: {response.text}")
            
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
                raise UserError(_("El Servicio Fiscal no devolvió ningún contenido para el archivo XML."))

            # Guardar el archivo en el wizard
            filename = f"ISLR_{agent_rif_clean}_{period}.xml"
            self.write({
                'xml_file': base64.b64encode(content),
                'xml_filename': filename,
                'state': 'done'
            })
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }

        except Exception as e:
            if isinstance(e, UserError):
                raise e
            _logger.error(f"[FISCAL-ISLR] Error al llamar al API XML ISLR: {str(e)}")
            raise UserError(_("No se pudo generar el archivo XML de ISLR. Por favor contacte con soporte técnico."))

    def action_confirm_declared(self):
        """
        Marca las retenciones como declaradas después de la descarga exitosa.
        """
        if self.mark_as_declared:
            self.wh_islr_ids.action_mark_as_declared()
        return {'type': 'ir.actions.act_window_close'}
