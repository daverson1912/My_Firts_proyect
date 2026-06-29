import requests
import json
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class WHubNoticeResolveWizard(models.TransientModel):
    _name = 'whub.notice.resolve.wizard'
    _description = 'Asistente para Resolver Errores de Mapeo de Avisos'

    log_id = fields.Many2one('whub.notice.sync.log', string='Log de Aviso', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Compañía', related='log_id.company_id', readonly=True)
    missing_entity = fields.Selection([('cliente', 'Cliente'), ('producto', 'Producto/Plan')], string='Entidad Faltante', readonly=True)

    # Campos de Cliente
    customer_name_wh = fields.Char('Cliente en WispHub', readonly=True)
    customer_id_wh = fields.Char('ID Cliente WispHub', readonly=True)
    odoo_partner_id = fields.Many2one('res.partner', string='Asociar con Contacto en Odoo',
                                      domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    # Campos de Producto/Plan
    concept_name_wh = fields.Char('Concepto/Plan en WispHub', readonly=True)
    concept_price_wh = fields.Float('Precio en WispHub', readonly=True)
    odoo_product_id = fields.Many2one('product.product', string='Asociar con Producto en Odoo',
                                      domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    def action_confirm_resolve(self):
        self.ensure_one()
        company = self.company_id
        
        if self.missing_entity == 'cliente':
            if not self.odoo_partner_id:
                raise UserError("Debe seleccionar un Contacto en Odoo para realizar la asociación.")
            
            # Asociar el ID de WispHub al Contacto seleccionado (soportando comas)
            partner = self.odoo_partner_id
            current_ids = [x.strip() for x in (partner.whub_customer_id or '').split(',') if x.strip()]
            if self.customer_id_wh and self.customer_id_wh not in current_ids:
                current_ids.append(self.customer_id_wh)
                partner.write({'whub_customer_id': ','.join(current_ids)})
                
        elif self.missing_entity == 'producto':
            if not self.odoo_product_id:
                raise UserError("Debe seleccionar un Producto en Odoo para realizar la asociación.")
            
            # Intentar encontrar el ID real de este plan/producto llamando a WispHub
            # Si no se puede, usaremos el nombre limpio como fallback en el ID
            whub_id = self._find_wisphub_id_by_name(self.concept_name_wh, company)
            target_id = whub_id or self.concept_name_wh
            
            # Asociar el ID al Producto seleccionado (soportando comas)
            product_tmpl = self.odoo_product_id.product_tmpl_id
            current_ids = [x.strip() for x in (product_tmpl.whub_product_id or '').split(',') if x.strip()]
            if target_id not in current_ids:
                current_ids.append(target_id)
                product_tmpl.write({'whub_product_id': ','.join(current_ids)})

        # Re-procesar el log inmediatamente después de guardar el mapeo
        self.log_id.action_reprocess()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Homologación Guardada',
                'message': 'Se ha guardado la homologación y se re-procesó el aviso correctamente.',
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }

    def _find_wisphub_id_by_name(self, name, company):
        """Busca el ID de un plan o artículo por su nombre consultando la API de WispHub."""
        url = (company.whub_middleware_url or '').strip().rstrip('/')
        api_key = (company.whub_api_key or "").strip()
        if not url or not api_key:
            return False
        
        headers = {'Content-Type': 'application/json'}
        payload = {"auth": {"api_key": api_key}, "filters": {}}
        
        try:
            # 1. Consultar planes simples
            res = requests.post(f"{url}/api/v1/wisphub/plans", json=payload, headers=headers, timeout=15)
            if res.status_code in (200, 201):
                data = res.json().get('data', {}).get('records') or res.json().get('records') or []
                for rec in data:
                    if rec.get('name') == name or rec.get('nombre') == name:
                        return str(rec.get('id', ''))
                        
            # 2. Consultar planes adicionales
            res = requests.post(f"{url}/api/v1/wisphub/additional-plans", json=payload, headers=headers, timeout=15)
            if res.status_code in (200, 201):
                data = res.json().get('data', {}).get('records') or res.json().get('records') or []
                for rec in data:
                    if rec.get('name') == name or rec.get('nombre') == name:
                        return str(rec.get('id', ''))
                        
            # 3. Consultar artículos
            res = requests.post(f"{url}/api/v1/wisphub/articles", json=payload, headers=headers, timeout=15)
            if res.status_code in (200, 201):
                data = res.json().get('data', {}).get('records') or res.json().get('records') or []
                for rec in data:
                    if rec.get('name') == name or rec.get('nombre') == name:
                        return str(rec.get('id', ''))
        except:
            pass
        return False


class WHubNoticeResolveBatchWizard(models.TransientModel):
    """
    Asistente de Resolución Masiva: analiza los registros seleccionados,
    agrupa y muestra todos los clientes y productos/planes no homologados
    para que el usuario los asocie a entidades de Odoo de una sola vez.
    """
    _name = 'whub.notice.resolve.batch.wizard'
    _description = 'Asistente de Resolución Masiva de Avisos'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    log_ids = fields.Many2many(
        'whub.notice.sync.log', 'whub_resolve_batch_log_rel',
        'wizard_id', 'log_id', string='Logs Seleccionados',
    )
    customer_line_ids = fields.One2many(
        'whub.notice.resolve.customer.line', 'wizard_id',
        string='Clientes No Homologados',
    )
    product_line_ids = fields.One2many(
        'whub.notice.resolve.product.line', 'wizard_id',
        string='Productos/Planes No Homologados',
    )
    total_selected = fields.Integer(string='Total Seleccionados', readonly=True)
    total_mapping_errors = fields.Integer(string='Errores de Mapeo', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            return res

        logs = self.env['whub.notice.sync.log'].browse(active_ids)
        mapping_logs = logs.filtered(lambda r: r.state == 'error_mapping')

        res['log_ids'] = [(6, 0, logs.ids)]
        res['total_selected'] = len(logs)
        res['total_mapping_errors'] = len(mapping_logs)

        customer_lines = []
        product_lines = []
        seen_customers = set()
        seen_products = set()

        for log in mapping_logs:
            try:
                notice_data = json.loads(log.raw_json) if log.raw_json else {}
            except Exception:
                continue

            if log.missing_entity == 'cliente':
                cid = str(notice_data.get('customer_id') or
                          notice_data.get('cliente', {}).get('id', ''))
                cname = (notice_data.get('cliente', {}).get('nombre') or
                         log.customer_name_wh or '')
                key = cid or cname
                if key and key not in seen_customers:
                    seen_customers.add(key)
                    customer_lines.append((0, 0, {
                        'customer_id_wh': cid,
                        'customer_name_wh': cname,
                    }))

            elif log.missing_entity == 'producto':
                details = (notice_data.get('items') or
                           notice_data.get('detalles') or [])
                for item in details:
                    concept = (item.get('description') or
                               item.get('concepto') or '')
                    price = float(item.get('price') or
                                  item.get('precio') or 0.0)
                    clean_name = self._extract_concept_name(concept, price)
                    if clean_name and clean_name not in seen_products:
                        seen_products.add(clean_name)
                        product_lines.append((0, 0, {
                            'concept_name_wh': clean_name,
                            'concept_price_wh': price,
                        }))

        res['customer_line_ids'] = customer_lines
        res['product_line_ids'] = product_lines
        return res

    @api.model
    def _extract_concept_name(self, concept, price):
        """Extrae el nombre limpio del plan/producto de la descripción del aviso."""
        concept_lines = [l.strip() for l in concept.split('\n') if l.strip()]

        def is_metadata(text):
            tl = text.lower()
            if 'periodo' in tl or ('del' in tl and 'al' in tl):
                return True
            if re.search(r'\d{1,2}/\w+/\d{2,4}', tl):
                return True
            if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', tl):
                return True
            return False

        clean_lines = [l for l in concept_lines if not is_metadata(l)]
        if not clean_lines:
            return concept.strip()

        cl = clean_lines[0]
        plan_match = re.search(r'(?i)plan\s+de\s+internet:\s*(.+)', cl)
        if plan_match:
            raw_name = plan_match.group(1).strip()
        elif ':' in cl:
            raw_name = cl.split(':', 1)[1].strip()
        else:
            raw_name = cl.strip()

        # Limpiar precio/monto al final
        cleaned = re.sub(r'\s+\d+\.\d+$', '', raw_name).strip()
        cleaned = re.sub(rf'\s+{re.escape(str(price))}$', '', cleaned).strip()
        price_int = int(price) if price == int(price) else None
        if price_int is not None:
            cleaned = re.sub(rf'\s+{re.escape(str(price_int))}$', '', cleaned).strip()
        return cleaned

    def action_confirm_resolve(self):
        """Guarda las asociaciones y re-procesa todos los avisos seleccionados."""
        self.ensure_one()
        company = self.company_id

        # 1. Guardar homologaciones de clientes
        for cline in self.customer_line_ids:
            if not cline.odoo_partner_id:
                continue
            partner = cline.odoo_partner_id
            current_ids = [x.strip() for x in
                           (partner.whub_customer_id or '').split(',') if x.strip()]
            if cline.customer_id_wh and cline.customer_id_wh not in current_ids:
                current_ids.append(cline.customer_id_wh)
                partner.write({'whub_customer_id': ','.join(current_ids)})

        # 2. Guardar homologaciones de productos/planes
        for pline in self.product_line_ids:
            if not pline.odoo_product_id:
                continue
            whub_id = self.env['whub.notice.resolve.wizard']._find_wisphub_id_by_name(
                pline.concept_name_wh, company)
            target_id = whub_id or pline.concept_name_wh
            product_tmpl = pline.odoo_product_id.product_tmpl_id
            current_ids = [x.strip() for x in
                           (product_tmpl.whub_product_id or '').split(',') if x.strip()]
            if target_id not in current_ids:
                current_ids.append(target_id)
                product_tmpl.write({'whub_product_id': ','.join(current_ids)})

        # 3. Re-procesar todos los logs seleccionados
        reprocessable = self.log_ids.filtered(lambda r: r.can_reprocess)
        success_count = 0
        failed_count = 0
        sync_engine = self.env['whub.notice.sync.engine']

        for rec in reprocessable:
            if not rec.raw_json:
                failed_count += 1
                continue
            try:
                notice_data = json.loads(rec.raw_json)
            except Exception:
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

        message = (f"Resolución masiva completada:\n"
                   f"- {success_count} avisos procesados exitosamente.\n"
                   f"- {failed_count} avisos aún con errores.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Resolución Masiva Completada',
                'message': message,
                'type': 'success' if failed_count == 0 else 'warning',
                'sticky': failed_count > 0,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }


class WHubNoticeResolveCustomerLine(models.TransientModel):
    _name = 'whub.notice.resolve.customer.line'
    _description = 'Línea de Cliente - Resolución Masiva'

    wizard_id = fields.Many2one('whub.notice.resolve.batch.wizard', ondelete='cascade')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id')
    customer_id_wh = fields.Char('ID WispHub', readonly=True)
    customer_name_wh = fields.Char('Nombre en WispHub', readonly=True)
    odoo_partner_id = fields.Many2one(
        'res.partner', string='Contacto en Odoo',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )


class WHubNoticeResolveProductLine(models.TransientModel):
    _name = 'whub.notice.resolve.product.line'
    _description = 'Línea de Producto - Resolución Masiva'

    wizard_id = fields.Many2one('whub.notice.resolve.batch.wizard', ondelete='cascade')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id')
    concept_name_wh = fields.Char('Concepto/Plan en WispHub', readonly=True)
    concept_price_wh = fields.Float('Precio', readonly=True)
    odoo_product_id = fields.Many2one(
        'product.product', string='Producto en Odoo',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
