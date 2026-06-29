import json
from odoo import fields, models, api
from odoo.exceptions import UserError


class WHubNoticeSyncLog(models.Model):
    """
    Log de Sincronización de Avisos de Cobro (Payment Notices).
    Registra cada intento de importación, permitiendo re-procesar fallos
    tras corregir homologaciones.
    """
    _name = 'whub.notice.sync.log'
    _description = 'Log de Sincronización de Avisos WispHub'
    _order = 'sync_date desc, id desc'
    _rec_name = 'whub_invoice_id'

    whub_invoice_id = fields.Char(string='ID Aviso WispHub', index=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, index=True)
    sync_date = fields.Datetime(string='Fecha de Sincronización', default=fields.Datetime.now)

    state = fields.Selection([
        ('success', 'Exitoso'),
        ('warning_skip', 'Advertencia (Omitido)'),
        ('error_mapping', 'Error de Mapeo'),
        ('error_connection', 'Error de Conexión'),
    ], string='Estado', required=True, default='success', index=True)

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta Generada')
    invoice_id = fields.Many2one('account.move', string='Factura Generada')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    customer_name_wh = fields.Char(string='Nombre Cliente WH')

    error_message = fields.Text(string='Detalle del Error')
    missing_entity = fields.Char(string='Entidad Faltante')
    raw_json = fields.Text(string='Información Técnica')

    can_reprocess = fields.Boolean(string='Puede Re-procesar', compute='_compute_can_reprocess', store=True)

    @api.depends('state')
    def _compute_can_reprocess(self):
        for rec in self:
            rec.can_reprocess = rec.state in ('error_mapping', 'error_connection')

    def action_reprocess(self):
        """Re-procesa un aviso que falló."""
        self.ensure_one()
        if not self.raw_json: return False
        try:
            notice_data = json.loads(self.raw_json)
        except: return False

        sync_engine = self.env['whub.notice.sync.engine']
        result = sync_engine._process_single_notice(notice_data, self.company_id)

        if result.get('success'):
            self.write({
                'state': 'success',
                'sale_order_id': result.get('sale_order_id'),
                'invoice_id': result.get('invoice_id'),
                'partner_id': result.get('partner_id'),
                'error_message': False,
                'missing_entity': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Re-procesamiento Exitoso',
                    'message': f"Aviso {self.whub_invoice_id} re-procesado y orden confirmada correctamente.",
                    'type': 'success',
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'}
                }
            }
        else:
            self.write({
                'state': result.get('state', 'error_other'),
                'error_message': result.get('error_message'),
                'missing_entity': result.get('missing_entity'),
            })
            if result.get('state') == 'error_mapping':
                return self.action_open_resolve_wizard(result)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error de Re-procesamiento',
                    'message': result.get('error_message') or "No se pudo re-procesar el aviso.",
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_open_resolve_wizard(self, result=None):
        self.ensure_one()
        missing_entity = self.missing_entity or (result and result.get('missing_entity'))
        
        customer_id_wh = ""
        customer_name_wh = self.customer_name_wh or ""
        concept_name_wh = ""
        concept_price_wh = 0.0
        
        try:
            notice_data = json.loads(self.raw_json)
            customer_id_wh = str(notice_data.get('customer_id') or notice_data.get('cliente', {}).get('id', ''))
            if not customer_name_wh:
                customer_name_wh = notice_data.get('cliente', {}).get('nombre') or customer_id_wh or ''
            
            details = notice_data.get('items') or notice_data.get('detalles') or []
            if details:
                first_item = details[0]
                concept_name_wh = first_item.get('description') or first_item.get('concepto') or 'Servicio WispHub'
                concept_price_wh = float(first_item.get('price') or first_item.get('precio') or 0.0)
        except:
            pass

        if missing_entity == 'producto' and concept_name_wh:
            # Extraer y limpiar nombre para sugerir en el wizard
            concept_lines = [l.strip() for l in concept_name_wh.split('\n') if l.strip()]
            clean_lines = [l for l in concept_lines if not ('periodo' in l.lower() or ('del' in l.lower() and 'al' in l.lower()))]
            if clean_lines:
                cl = clean_lines[0]
                import re
                plan_match = re.search(r'(?i)plan\s+de\s+internet:\s*(.+)', cl)
                if plan_match:
                    raw_name = plan_match.group(1).strip()
                    cleaned = re.sub(r'\s+\d+\.\d+$', '', raw_name).strip()
                    cleaned = re.sub(rf'\s+{re.escape(str(concept_price_wh))}$', '', cleaned).strip()
                    concept_name_wh = cleaned
                else:
                    if ':' in cl:
                        raw_name = cl.split(':', 1)[1].strip()
                    else:
                        raw_name = cl.strip()
                    cleaned = re.sub(r'\s+\d+\.\d+$', '', raw_name).strip()
                    cleaned = re.sub(rf'\s+{re.escape(str(concept_price_wh))}$', '', cleaned).strip()
                    concept_name_wh = cleaned

        wizard = self.env['whub.notice.resolve.wizard'].create({
            'log_id': self.id,
            'missing_entity': 'cliente' if missing_entity == 'cliente' else 'producto',
            'customer_name_wh': customer_name_wh,
            'customer_id_wh': customer_id_wh,
            'concept_name_wh': concept_name_wh,
            'concept_price_wh': concept_price_wh,
        })
        
        return {
            'name': 'Corregir Homologación Faltante',
            'type': 'ir.actions.act_window',
            'res_model': 'whub.notice.resolve.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reprocess_multi(self):
        """Re-procesa múltiples avisos seleccionados que fallaron."""
        reprocessables = self.filtered(lambda r: r.can_reprocess)
        if not reprocessables:
            raise UserError("Ninguno de los registros seleccionados se puede re-procesar (deben estar en error de mapeo u otro error).")
        
        # Si hay errores de mapeo, abrir el wizard de resolución masiva
        mapping_errors = reprocessables.filtered(lambda r: r.state == 'error_mapping')
        if mapping_errors:
            return {
                'name': 'Validación de Homologaciones Pendientes',
                'type': 'ir.actions.act_window',
                'res_model': 'whub.notice.resolve.batch.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {**self.env.context, 'active_ids': reprocessables.ids},
            }
        
        # Si solo hay errores de conexión (sin mapeo), re-procesar directamente
        success_count = 0
        failed_count = 0
        sync_engine = self.env['whub.notice.sync.engine']
        
        for rec in reprocessables:
            if not rec.raw_json:
                failed_count += 1
                continue
            try:
                notice_data = json.loads(rec.raw_json)
            except:
                failed_count += 1
                continue

            result = sync_engine._process_single_notice(notice_data, rec.company_id)

            if result.get('success'):
                rec.write({
                    'state': 'success',
                    'sale_order_id': result.get('sale_order_id'),
                    'invoice_id': result.get('invoice_id'),
                    'partner_id': result.get('partner_id'),
                    'error_message': False,
                    'missing_entity': False,
                })
                success_count += 1
            else:
                rec.write({
                    'state': result.get('state', 'error_other'),
                    'error_message': result.get('error_message'),
                    'missing_entity': result.get('missing_entity'),
                })
                failed_count += 1
                
        message = f"Proceso de re-procesamiento completado:\n- {success_count} exitosos.\n- {failed_count} fallidos."
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Re-procesamiento Masivo',
                'message': message,
                'type': 'success' if failed_count == 0 else 'warning',
                'sticky': failed_count > 0,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }

    @api.model
    def _auto_reprocess_failed_logs(self, company_id=None):
        """
        Busca y re-procesa automáticamente los logs fallidos (error_mapping, error_other)
        que ahora puedan tener sus mapeos resueltos.
        """
        domain = [('state', 'in', ('error_mapping', 'error_connection'))]
        if company_id:
            domain.append(('company_id', '=', company_id))
        failed_logs = self.search(domain)
        if failed_logs:
            sync_engine = self.env['whub.notice.sync.engine']
            for rec in failed_logs:
                if not rec.raw_json:
                    continue
                try:
                    notice_data = json.loads(rec.raw_json)
                except:
                    continue
                result = sync_engine._process_single_notice(notice_data, rec.company_id)
                if result.get('success'):
                    rec.write({
                        'state': 'success',
                        'sale_order_id': result.get('sale_order_id'),
                        'invoice_id': result.get('invoice_id'),
                        'partner_id': result.get('partner_id'),
                        'error_message': False,
                        'missing_entity': False,
                    })
                else:
                    rec.write({
                        'state': result.get('state', 'error_other'),
                        'error_message': result.get('error_message'),
                        'missing_entity': result.get('missing_entity'),
                    })

    def action_open_homologation(self):
        return self.env['res.config.settings'].action_open_homologation_wizard()

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id: return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id: return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_date_wizard(self):
        """Abre el wizard para consultar avisos por fechas."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whub.notice.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }
