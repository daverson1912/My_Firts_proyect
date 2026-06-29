import json
import requests
import logging
import re
from datetime import datetime, timedelta, time
from psycopg2 import IntegrityError

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.modules.module import get_module_resource

_logger = logging.getLogger(__name__)


class WHubNoticeSyncEngine(models.AbstractModel):
    """
    Motor de sincronización de Avisos de Cobro (Payment Notices) WispHub → Odoo.
    Transforma cada aviso en un sale.order confirmado, con sincronización 
    incremental y control anti-duplicados.
    """
    _name = 'whub.notice.sync.engine'
    _description = 'Motor de Sincronización de Avisos de Cobro WispHub'

    # ==========================================================================
    # MÉTODO PRINCIPAL: SINCRONIZACIÓN COMPLETA
    # ==========================================================================

    @api.model
    def action_sync_payment_notices(self):
        """
        Punto de entrada del CRON (cada 20 minutos).
        Continúa automáticamente desde la fecha/hora de la última orden sincronizada
        (whub_sync_inv). Si todavía no hay un punto de partida definido, no hace nada:
        el usuario debe configurarlo una primera vez con el botón "Sincronizar Avisos de Cobro".
        """
        company = self.env.company
        if not company.whub_sync_inv:
            _logger.info(
                "WispHub Sync Notices (Cron): aún no se ha definido un punto de partida para %s. "
                "Use el botón 'Sincronizar Avisos de Cobro' en Ajustes para configurarlo.",
                company.name
            )
            return False

        return self._run_notice_sync(
            company, company.whub_sync_inv, fields.Datetime.now(), "WispHub Sync Notices (Cron)"
        )

    @api.model
    def action_sync_payment_notices_from(self, date_from):
        """
        Punto de entrada manual (botón/wizard "Sincronizar Avisos de Cobro").
        Trae todas las órdenes desde el punto de partida elegido hasta ahora,
        y deja ese punto de partida guardado para que el cron continúe desde ahí.
        """
        company = self.env.company
        return self._run_notice_sync(
            company, date_from, fields.Datetime.now(), "WispHub Sync Notices (Manual)"
        )

    @api.model
    def _run_notice_sync(self, company, date_from_dt, date_to_dt, log_context):
        """ Lógica compartida: consulta, procesa y avanza el punto de partida (whub_sync_inv). """
        url = (company.whub_middleware_url or '').strip().rstrip('/')
        if not url:
            raise UserError("No se ha configurado la URL del Middleware en los Ajustes de WispHub.")

        api_key = (company.whub_api_key or "").strip()
        if not api_key:
            raise UserError("No se ha configurado la API Key de WispHub. Vaya a Ajustes → WispHub.")

        headers = {'Content-Type': 'application/json'}

        _logger.info(
            "%s: Consultando avisos desde %s hasta %s para compañía %s",
            log_context, date_from_dt, date_to_dt, company.name
        )

        # WispHub no acepta rangos de más de 3 meses: se divide la consulta en
        # bloques de máximo 90 días y se consultan en secuencia.
        notices = []
        first_notice = None
        for window_from, window_to in self._split_date_range(date_from_dt, date_to_dt):
            base_filters = {
                'date_from': window_from.strftime('%Y-%m-%d'),
                'date_to': (window_to + timedelta(days=1)).strftime('%Y-%m-%d'),
            }
            _logger.info(
                "%s: Bloque %s -> %s", log_context, base_filters['date_from'], base_filters['date_to']
            )
            window_notices, response_keys, window_first_notice = self._fetch_paginated_notices(
                url=url,
                headers=headers,
                api_key=api_key,
                base_filters=base_filters,
                company=company,
                log_context=log_context
            )
            notices.extend(window_notices)
            if window_first_notice and not first_notice:
                first_notice = window_first_notice

        _logger.info(
            "%s: Recibidos %d avisos en total.",
            log_context, len(notices)
        )
        if first_notice:
            _logger.debug("%s: Primer aviso: %s", log_context, json.dumps(first_notice, indent=2))

        # --- Procesar cada aviso ---
        success_count = 0
        error_count = 0
        skipped_count = 0
        max_notice_date = None

        for notice in notices:
            notice_id = str(notice.get('id', ''))

            notice_date = self._parse_notice_date(notice)
            if notice_date and (not max_notice_date or notice_date > max_notice_date):
                max_notice_date = notice_date

            # Anti-duplicados
            existing = self.env['sale.order'].search([
                ('whub_invoice_id', '=', notice_id),
                ('company_id', '=', company.id)
            ], limit=1)

            if existing:
                skipped_count += 1
                continue

            result = self._process_single_notice(notice, company)
            if result.get('success') and result.get('skipped'):
                skipped_count += 1
            elif result.get('success'):
                success_count += 1
            else:
                error_count += 1

        # --- Avanzar el punto de partida: lo más reciente entre la última orden vista
        #     y el límite hasta donde se consultó (para no repetir el rango ya revisado). ---
        new_mark = max_notice_date or date_to_dt
        if not company.whub_sync_inv or new_mark > company.whub_sync_inv:
            company.sudo().write({'whub_sync_inv': new_mark})

        # --- Notificación al usuario ---
        msg_parts = []
        if success_count: msg_parts.append(f"✅ {success_count} órdenes creadas")
        if skipped_count: msg_parts.append(f"⏭️ {skipped_count} ya existían")
        if error_count: msg_parts.append(f"❌ {error_count} con errores")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización de Avisos de Cobro',
                'message': '\n'.join(msg_parts) or "No se encontraron avisos nuevos.",
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': error_count > 0,
            }
        }

    @api.model
    def _split_date_range(self, date_from_dt, date_to_dt, max_days=80):
        """ Divide un rango de fechas en bloques de máximo `max_days` días
        (WispHub rechaza rangos de más de 3 meses). """
        if date_from_dt >= date_to_dt:
            yield (date_from_dt, date_to_dt)
            return
        window_start = date_from_dt
        while window_start < date_to_dt:
            window_end = min(window_start + timedelta(days=max_days), date_to_dt)
            yield (window_start, window_end)
            window_start = window_end

    @api.model
    def _parse_notice_date(self, notice):
        """ Extrae la fecha/hora del aviso (issue_date o date) como datetime, si es posible. """
        raw = notice.get('issue_date') or notice.get('date')
        if not raw:
            return None
        raw = str(raw)[:10]  # Tomar solo YYYY-MM-DD
        try:
            dt = datetime.strptime(raw, '%Y-%m-%d')
            # Retornar combinando con las 12:00:00 PM (mediodía) para evitar desfases de zona horaria local en Odoo
            return datetime.combine(dt.date(), time(12, 0, 0))
        except ValueError:
            pass
        return None

    # ==========================================================================
    # PROCESAMIENTO DE UN AVISO INDIVIDUAL
    # ==========================================================================

    @api.model
    def _parse_whub_date(self, raw):
        """ Parsea una fecha simple (YYYY-MM-DD o DD/MM/YYYY, con o sin hora) reportada por WispHub. """
        if not raw:
            return False
        raw = str(raw).strip()
        date_part = raw.split(' ')[0]
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue
        return False

    @api.model
    def _get_or_create_sale_tax(self, company, percentage):
        """ Busca el impuesto de venta de la compañía para el porcentaje exacto
        reportado por WispHub; si no existe, lo crea (reutilizable en próximos avisos). """
        if percentage <= 0:
            return False
        # Tolerancia para evitar crear impuestos casi idénticos por imprecisión decimal
        # (ej. 16.0% y 16.01% en distintos avisos deben tratarse como el mismo impuesto).
        candidates = self.env['account.tax'].search([
            ('company_id', '=', company.id),
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
        ])
        tax = candidates.filtered(lambda t: abs(t.amount - percentage) <= 0.1)[:1]
        if not tax:
            # Buscar o crear el grupo de impuestos para este porcentaje para evitar etiquetas incorrectas
            group_name = f'Impuesto del {percentage}%'
            tax_group = self.env['account.tax.group'].search([
                ('name', '=', group_name),
                '|', ('company_id', '=', company.id), ('company_id', '=', False)
            ], limit=1)
            if not tax_group:
                tax_group = self.env['account.tax.group'].create({
                    'name': group_name,
                    'company_id': company.id,
                })
            
            tax = self.env['account.tax'].create({
                'name': f'{percentage}%',
                'amount': percentage,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'company_id': company.id,
                'tax_group_id': tax_group.id,
            })
            _logger.info("WispHub: creado impuesto de venta '%s' con grupo '%s' para compañía %s", tax.name, tax_group.name, company.name)
        return tax

    @api.model
    def _build_whub_reference_vals(self, notice_data):
        """ Extrae los datos de referencia del aviso (monto, descuento, impuestos, estado, etc.)
        para no perder información del aviso original aunque no se use en el cálculo de Odoo. """
        return {
            'whub_status': notice_data.get('status') or notice_data.get('estado') or False,
            'whub_due_date': self._parse_whub_date(notice_data.get('due_date') or notice_data.get('fecha_vencimiento')),
            'whub_payment_date': self._parse_whub_date(notice_data.get('payment_date') or notice_data.get('fecha_pago')),
            'whub_amount': float(notice_data.get('amount') or notice_data.get('total') or 0.0),
            'whub_sub_total': float(notice_data.get('sub_total') or notice_data.get('subtotal') or 0.0),
            'whub_discount': float(notice_data.get('discount') or notice_data.get('descuento') or 0.0),
            'whub_total_taxes': float(notice_data.get('total_taxes') or notice_data.get('impuesto') or 0.0),
            'whub_total_collected': float(notice_data.get('total_collected') or notice_data.get('total_cobrado') or 0.0),
            'whub_retention_percentage': float(notice_data.get('retention_percentage') or notice_data.get('porcentaje_retencion') or 0.0),
            'whub_total_retentions': float(notice_data.get('total_retentions') or notice_data.get('valor_retencion') or 0.0),
        }

    @api.model
    def _write_or_create_log(self, vals):
        """Busca si ya existe un log de aviso para esta factura y compañía y lo actualiza, o crea uno nuevo."""
        log_record = self.env['whub.notice.sync.log'].search([
            ('whub_invoice_id', '=', vals.get('whub_invoice_id')),
            ('company_id', '=', vals.get('company_id'))
        ], limit=1)
        if log_record:
            log_record.write(vals)
        else:
            self.env['whub.notice.sync.log'].create(vals)

    @api.model
    def _process_single_notice(self, notice_data, company):
        """
        Crea o busca orden de venta para un aviso específico.
        Si hay problemas con clientes o productos, registra error en el Log.
        """
        notice_id = str(notice_data.get('id', ''))
        
        # Extraer el ID y nombre del cliente soportando ambas estructuras del JSON
        customer_id_wh = str(notice_data.get('customer_id') or notice_data.get('cliente', {}).get('id', ''))
        customer_name = notice_data.get('cliente', {}).get('nombre') or notice_data.get('customer_id') or ''
        
        raw_json = json.dumps(notice_data, ensure_ascii=False)

        # 1. Validar existencia del cliente homologado (solo si tenemos un ID válido para evitar falsos positivos con valores vacíos o nulos)
        partner = False
        if customer_id_wh and customer_id_wh.strip() and customer_id_wh not in ('False', 'None', '0'):
            w_id = customer_id_wh.strip()
            # Buscar soportando múltiples IDs separados por coma y contactos globales/compartidos (company_id = False)
            domain = [
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
                '|', ('whub_customer_id', '=', w_id),
                '|', ('whub_customer_id', '=ilike', f'{w_id},%'),
                '|', ('whub_customer_id', '=ilike', f'%,{w_id}'),
                     ('whub_customer_id', '=ilike', f'%,{w_id},%')
            ]
            partner = self.env['res.partner'].search(domain, limit=1)

        if not partner:
            err_msg = f"El cliente WispHub '{customer_name}' (ID {customer_id_wh}) no está homologado en Odoo."
            self._write_or_create_log({
                'whub_invoice_id': notice_id,
                'company_id': company.id,
                'state': 'error_mapping',
                'missing_entity': 'cliente',
                'error_message': err_msg,
                'customer_name_wh': customer_name,
                'raw_json': raw_json,
            })
            return {
                'success': False,
                'error': 'client_missing',
                'state': 'error_mapping',
                'missing_entity': 'cliente',
                'error_message': err_msg
            }

        # 2. Construir líneas de la orden (soportando 'items' y 'detalles')
        order_lines = []
        details = notice_data.get('items') or notice_data.get('detalles') or []
        if not details:
            # Si no hay detalles, agregamos el total del aviso como un genérico
            details = [{
                'concepto': f"Aviso de Cobro WispHub #{notice_id}",
                'precio': float(notice_data.get('total') or notice_data.get('amount') or 0.0),
                'plan_id': None,
                'articulo_id': None
            }]

        for line in details:
            concept = line.get('description') or line.get('concepto') or 'Servicio WispHub'
            price = float(line.get('price') or line.get('precio') or 0.0)
            # Cantidad real reportada por WispHub (antes se forzaba siempre a 1).
            quantity = float(line.get('quantity') or line.get('cantidad') or 1.0)
            # El item real trae 'id' (sirve para plan o artículo, ambos se guardan
            # en whub_product_id); se mantiene compatibilidad con plan_id/articulo_id legados.
            item_id = str(line.get('id') or line.get('plan_id') or line.get('articulo_id') or '') or None

            # Buscar producto mapeado usando whub_product_id (soporta comas)
            # y permitiendo productos globales (company_id = False)
            product = False
            if item_id:
                product = self.env['product.product'].search([
                    '|', ('company_id', '=', False), ('company_id', '=', company.id),
                    '|', ('whub_product_id', '=', item_id),
                    '|', ('whub_product_id', '=ilike', f'{item_id},%'),
                    '|', ('whub_product_id', '=ilike', f'%,{item_id}'),
                         ('whub_product_id', '=ilike', f'%,{item_id},%')
                ], limit=1)

            # FALLBACK DE DOBLE VALIDACIÓN POR DESCRIPCIÓN (Extraer nombre e ignorar monto/tiempo al final)
            if not product and concept:
                # 1. Separar concepto por líneas y filtrar metadatos/periodos
                concept_lines = [l.strip() for l in concept.split('\n') if l.strip()]
                
                # Función auxiliar para identificar si es metadato de fecha/periodo
                def is_metadata(text):
                    text_lower = text.lower()
                    if 'periodo' in text_lower or ('del' in text_lower and 'al' in text_lower):
                        return True
                    if re.search(r'\d{1,2}/\w+/\d{2,4}', text_lower) or re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', text_lower):
                        return True
                    return False
                
                clean_lines = [l for l in concept_lines if not is_metadata(l)]
                
                # Buscar candidatos de planes y productos
                plan_candidate = None
                product_candidates = []
                
                for cl in clean_lines:
                    # Detectar si tiene formato de Plan
                    plan_match = re.search(r'(?i)plan\s+de\s+internet:\s*(.+)', cl)
                    if plan_match:
                        raw_name = plan_match.group(1).strip()
                        # Limpiar precio/monto al final (decimales o entero exacto)
                        cleaned = re.sub(r'\s+\d+\.\d+$', '', raw_name).strip()
                        cleaned = re.sub(rf'\s+{re.escape(str(price))}$', '', cleaned).strip()
                        price_int = int(price) if price == int(price) else None
                        if price_int is not None:
                            cleaned = re.sub(rf'\s+{re.escape(str(price_int))}$', '', cleaned).strip()
                        plan_candidate = cleaned
                    else:
                        # Para otras líneas (ej. Renta y mantenimiento de la red: ...)
                        # Si tiene colon, separar por el primero
                        if ':' in cl:
                            parts = cl.split(':', 1)
                            raw_name = parts[1].strip()
                        else:
                            raw_name = cl.strip()
                        
                        cleaned = re.sub(r'\s+\d+\.\d+$', '', raw_name).strip()
                        cleaned = re.sub(rf'\s+{re.escape(str(price))}$', '', cleaned).strip()
                        price_int = int(price) if price == int(price) else None
                        if price_int is not None:
                            cleaned = re.sub(rf'\s+{re.escape(str(price_int))}$', '', cleaned).strip()
                        if cleaned:
                            product_candidates.append(cleaned)
                
                # Intentar buscar primero el plan si existe
                if plan_candidate:
                    # A. Buscar en homologación de planes (transientes)
                    plan_line_rec = self.env['whub.homologation.plan.line'].search([
                        ('whub_plan_name', '=', plan_candidate),
                        ('wizard_id.company_id', '=', company.id)
                    ], limit=1)
                    if plan_line_rec and plan_line_rec.odoo_product_id:
                        product = plan_line_rec.odoo_product_id
                    
                    # B. Buscar por nombre directo en Odoo (global o compañía)
                    if not product:
                        product = self.env['product.product'].search([
                            '|', ('company_id', '=', False), ('company_id', '=', company.id),
                            ('name', '=', plan_candidate)
                        ], limit=1)
                
                # Si no se encontró el plan o no había plan_candidate, intentar con productos
                if not product:
                    for prod_candidate in product_candidates:
                        # A. Buscar en homologación de productos (transientes)
                        prod_line_rec = self.env['whub.homologation.product.line'].search([
                            ('whub_product_name', '=', prod_candidate),
                            ('wizard_id.company_id', '=', company.id)
                        ], limit=1)
                        if prod_line_rec and prod_line_rec.odoo_product_id:
                            product = prod_line_rec.odoo_product_id
                            break
                        
                        # B. Buscar por nombre directo del candidato en Odoo (global o compañía)
                        product = self.env['product.product'].search([
                            '|', ('company_id', '=', False), ('company_id', '=', company.id),
                            ('name', '=', prod_candidate)
                        ], limit=1)
                        if product:
                            break
            
            # Si no se encuentra mapeo, usar un genérico o fallar
            if not product:
                # Buscamos un producto comodín de servicio (global o compañía)
                product = self.env['product.product'].search([
                    '|', ('company_id', '=', False), ('company_id', '=', company.id),
                    ('default_code', '=', 'WHUB_SERVICE')
                ], limit=1)
                
            if not product:
                # Si no hay producto genérico de servicio, fallamos
                err_msg = f"No se encontró mapeo para el concepto '{concept}' ni un producto comodín WHUB_SERVICE."
                self._write_or_create_log({
                    'whub_invoice_id': notice_id,
                    'company_id': company.id,
                    'state': 'error_mapping',
                    'missing_entity': 'producto',
                    'error_message': err_msg,
                    'partner_id': partner.id,
                    'customer_name_wh': customer_name,
                    'raw_json': raw_json,
                })
                return {
                    'success': False,
                    'error': 'product_missing',
                    'state': 'error_mapping',
                    'missing_entity': 'producto',
                    'error_message': err_msg
                }

            order_lines.append((0, 0, {
                'product_id': product.id,
                'name': concept,
                'product_uom_qty': quantity,
                'price_unit': price,
            }))

        # El subtotal/impuesto reportado por WispHub no se refleja por defecto en las
        # líneas (los productos de WispHub se crean sin impuestos). Se aplica aquí el
        # impuesto real para que el Total de la orden coincida con lo realmente cobrado.
        sub_total = float(notice_data.get('sub_total') or notice_data.get('subtotal') or 0.0)
        total_taxes = float(notice_data.get('total_taxes') or notice_data.get('impuesto') or 0.0)
        if sub_total > 0 and total_taxes > 0:
            tax_percentage = round((total_taxes / sub_total) * 100, 2)
            tax = self._get_or_create_sale_tax(company, tax_percentage)
            if tax:
                for line_vals in order_lines:
                    line_vals[2]['tax_id'] = [(6, 0, [tax.id])]

        # 3. Crear y confirmar la Orden de Venta
        try:
            with self.env.cr.savepoint():
                sale_order = self.env['sale.order'].create({
                    'partner_id': partner.id,
                    'company_id': company.id,
                    'whub_invoice_id': notice_id,
                    'date_order': notice_data.get('issue_date') or notice_data.get('date') or fields.Datetime.now(),
                    'order_line': order_lines,
                    **self._build_whub_reference_vals(notice_data),
                })

                sale_order.action_confirm()

                # Evitar que Odoo sobrescriba date_order con fields.Datetime.now() durante action_confirm()
                notice_date = self._parse_notice_date(notice_data) or fields.Datetime.now()
                sale_order.write({'date_order': notice_date})

                invoice_id = False
                # whatsapp_enabled se puede verificar o forzar
                # sale_order.action_whub_send_whatsapp()

                # Registrar éxito en el Log de Avisos
                self._write_or_create_log({
                    'whub_invoice_id': notice_id,
                    'company_id': company.id,
                    'state': 'success',
                    'sale_order_id': sale_order.id,
                    'invoice_id': invoice_id,
                    'partner_id': partner.id,
                    'customer_name_wh': customer_name,
                    'raw_json': raw_json,
                    'error_message': False,
                    'missing_entity': False,
                })
                return {'success': True, 'sale_order_id': sale_order.id, 'invoice_id': invoice_id, 'partner_id': partner.id}
        except IntegrityError:
            existing = self.env['sale.order'].search([
                ('whub_invoice_id', '=', notice_id),
                ('company_id', '=', company.id)
            ], limit=1)
            if existing:
                return {
                    'success': True,
                    'skipped': True,
                    'sale_order_id': existing.id,
                    'invoice_id': False,
                    'partner_id': existing.partner_id.id,
                }
            return {
                'success': False,
                'error': 'database_conflict',
                'state': 'error_connection',
                'error_message': 'Error de integridad al guardar la orden de venta.'
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = f"Error inesperado: {str(e)}"
            self._write_or_create_log({
                'whub_invoice_id': notice_id,
                'company_id': company.id,
                'state': 'error_connection',
                'error_message': err_msg,
                'partner_id': partner.id,
                'customer_name_wh': customer_name,
                'raw_json': raw_json,
            })
            return {
                'success': False,
                'error': 'unexpected',
                'state': 'error_connection',
                'error_message': err_msg
            }

    # ==========================================================================
    # MÉTODOS DE SOPORTE E INTEGRACIÓN
    # ==========================================================================

    @api.model
    def _normalize_status(self, value):
        return (value or '').strip().lower()

    @api.model
    def _get_allowed_statuses(self):
        """Lee estados permitidos desde los ajustes de la compañía."""
        company = self.env.company
        raw_statuses = company.whub_allowed_notice_statuses

        if not raw_statuses:
            return set()

        if isinstance(raw_statuses, str):
            statuses = [self._normalize_status(s) for s in raw_statuses.split(',')]
            return set([s for s in statuses if s])

        return set()

    @api.model
    def _is_allowed_notice_status(self, notice, allowed_statuses):
        """Valida estado según configuración; si no hay configuración, no filtra."""
        if not allowed_statuses:
            return True
        status = self._normalize_status(notice.get('status'))
        if not status:
            return True
        return status in allowed_statuses

    @api.model
    def _fetch_paginated_notices(self, url, headers, api_key, base_filters, company, log_context):
        """Consulta avisos paginados hasta agotar resultados, aplicando filtros y estados permitidos."""
        allowed_statuses = self._get_allowed_statuses()
        limit = self._get_notice_page_size(company)
        notices = []
        response_keys = set()
        first_notice = None
        offset = 0

        while True:
            payload = {
                "auth": {"api_key": api_key},
                "filters": {
                    **base_filters,
                    'limit': limit,
                    'offset': offset,
                }
            }

            try:
                response = requests.post(
                    f"{url}/api/v1/wisphub/invoices",
                    json=payload, headers=headers, timeout=30
                )
            except requests.exceptions.ConnectionError:
                self._log_error_no_notice(company, 'error_connection', 'Error de conexión con Middleware.')
                raise UserError("No se pudo conectar con el Middleware de WispHub.")
            except requests.exceptions.Timeout:
                self._log_error_no_notice(company, 'error_timeout', 'Tiempo de espera agotado al conectar con Middleware.')
                raise UserError("El Middleware de WispHub no respondió a tiempo.")

            if response.status_code == 401:
                self._log_error_no_notice(company, 'error_auth', 'API Key de WispHub no válida.')
                raise UserError("La API Key configurada no es válida en WispHub.")

            # Intentar leer el JSON de la respuesta sin importar el status code,
            # para poder mostrar el mensaje de error real del middleware.
            valid_json = True
            try:
                data = response.json()
            except Exception:
                data = {}
                valid_json = False

            if response.status_code not in (200, 201):
                detail = (data.get('message') or data.get('error_desc') or data.get('detail')) if isinstance(data, dict) else None
                self._log_error_no_notice(company, 'error_http', f"Middleware respondió con status {response.status_code}: {detail or 'sin detalle'}")
                raise UserError(f"Error en Middleware (HTTP {response.status_code}): {detail or 'sin detalle adicional.'}")

            if not valid_json:
                self._log_error_no_notice(company, 'error_json', 'Middleware no devolvió un JSON válido.')
                raise UserError("Respuesta no válida del Middleware.")

            if isinstance(data, dict) and data.get('error'):
                self._log_error_no_notice(company, 'error_api', data.get('message', 'Error desconocido en API.'))
                raise UserError(f"API Error: {data.get('message')}")

            batch = self._extract_records(data)
            if isinstance(data, dict):
                response_keys.update(data.keys())

            filtered_batch = [n for n in batch if self._is_allowed_notice_status(n, allowed_statuses)]
            if filtered_batch and not first_notice:
                first_notice = filtered_batch[0]
            notices.extend(filtered_batch)

            if not batch or len(batch) < limit:
                break
            offset += limit

        return notices, list(response_keys), first_notice

    @api.model
    def _get_notice_page_size(self, company):
        """Obtiene tamaño de página para avisos desde res.company."""
        value = company.whub_customers_page_size or 100
        try:
            value = int(value)
            return value if value > 0 else 100
        except (TypeError, ValueError):
            return 100

    @api.model
    def _extract_records(self, data):
        """ Extrae los registros de avisos/facturas del payload """
        if isinstance(data, list): return data
        for key in ['records', 'invoices', 'items', 'data']:
            if key in data:
                inner = data[key]
                if isinstance(inner, list): return inner
                if isinstance(inner, dict):
                    if 'records' in inner: return inner['records']
                    if 'data' in inner and isinstance(inner['data'], dict) and 'records' in inner['data']:
                        return inner['data']['records']
        for key in ['records', 'invoices', 'items']:
            if key in data and isinstance(data[key], list): return data[key]
        return []

    @api.model
    def _log_error_no_notice(self, company, error_type, message):
        """ Registra errores generales de sincronización global (sin aviso asociado) """
        connection_types = ('error_connection', 'error_timeout')
        state = 'error_connection' if error_type in connection_types else 'error_other'
        self.env['whub.notice.sync.log'].create({
            'company_id': company.id,
            'state': state,
            'missing_entity': error_type,
            'error_message': message,
        })
