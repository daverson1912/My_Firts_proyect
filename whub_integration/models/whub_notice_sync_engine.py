import json
import requests
import logging
from datetime import timedelta
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
        Punto de entrada principal para el flujo de avisos de cobro.
        1. Lee la fecha de última sincronización desde res.company
        2. Consulta la API con el margen configurado
        3. Procesa cada aviso (crea SO o registra error)
        4. Actualiza la fecha de sincronización en res.company
        """
        company = self.env.company

        # --- Configuración de la API desde Ajustes ---
        url = (company.whub_middleware_url or '').strip().rstrip('/')
        if not url:
            raise UserError("No se ha configurado la URL del Middleware en los Ajustes de WispHub.")

        api_key = (company.whub_api_key or "").strip()
        if not api_key:
            raise UserError("No se ha configurado la API Key de WispHub. Vaya a Ajustes → WispHub.")

        # --- Calcular fecha de filtro con margen de seguridad ---
        days_back = company.whub_notice_sync_days_back or 30
        last_sync = company.whub_sync_inv or fields.Datetime.now()
        date_from = (last_sync - timedelta(days=days_back)).strftime('%Y-%m-%d')
        date_to = (fields.Date.context_today(self) + timedelta(days=1)).strftime('%Y-%m-%d')

        headers = {'Content-Type': 'application/json'}
        base_filters = {
            'date_from': date_from,
            'date_to': date_to
        }

        _logger.info(
            "WispHub Sync Notices: Consultando avisos desde %s para compañía %s (days_back=%s)",
            date_from, company.name, days_back
        )

        notices, response_keys, first_notice = self._fetch_paginated_notices(
            url=url,
            headers=headers,
            api_key=api_key,
            base_filters=base_filters,
            company=company,
            log_context="WispHub Sync Notices"
        )

        _logger.info(
            "WispHub Sync Notices: Recibidos %d avisos. Claves en respuesta: %s",
            len(notices), response_keys
        )
        if first_notice:
            _logger.debug("WispHub Sync Notices: Primer aviso: %s", json.dumps(first_notice, indent=2))

        # --- Procesar cada aviso ---
        success_count = 0
        error_count = 0
        skipped_count = 0

        for notice in notices:
            notice_id = str(notice.get('id', ''))

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

        # --- Actualizar fecha de sincronización en res.company ---
        company.sudo().write({
            'whub_sync_inv': fields.Datetime.now()
        })

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

    # ==========================================================================
    # PROCESAMIENTO DE UN AVISO INDIVIDUAL
    # ==========================================================================

    @api.model
    def _process_single_notice(self, notice_data, company):
        """
        Crea o busca orden de venta para un aviso específico.
        Si hay problemas con clientes o productos, registra error en el Log.
        """
        notice_id = str(notice_data.get('id', ''))
        customer_id_wh = str(notice_data.get('cliente', {}).get('id', ''))
        customer_name = notice_data.get('cliente', {}).get('nombre', '')
        
        raw_json = json.dumps(notice_data, ensure_ascii=False)

        # 1. Validar existencia del cliente homologado
        partner = self.env['res.partner'].search([
            ('whub_customer_id', '=', customer_id_wh),
            ('company_id', '=', company.id)
        ], limit=1)

        if not partner:
            self.env['whub.notice.sync.log'].create({
                'whub_invoice_id': notice_id,
                'company_id': company.id,
                'state': 'error',
                'error_type': 'client_missing',
                'error_message': f"El cliente WispHub '{customer_name}' (ID {customer_id_wh}) no está homologado en Odoo.",
                'customer_name_wh': customer_name,
                'raw_json': raw_json,
            })
            return {'success': False, 'error': 'client_missing'}

        # 2. Construir líneas de la orden
        order_lines = []
        details = notice_data.get('detalles', [])
        if not details:
            # Si no hay detalles, agregamos el total del aviso como un genérico
            details = [{
                'concepto': f"Aviso de Cobro WispHub #{notice_id}",
                'precio': float(notice_data.get('total', 0.0)),
                'plan_id': None,
                'articulo_id': None
            }]

        for line in details:
            concept = line.get('concepto', 'Servicio WispHub')
            price = float(line.get('precio', 0.0))
            plan_id = str(line.get('plan_id', '')) if line.get('plan_id') else None
            article_id = str(line.get('articulo_id', '')) if line.get('articulo_id') else None

            # Buscar producto mapeado por plan o artículo
            product = False
            if plan_id:
                product = self.env['product.product'].search([
                    ('whub_plan_id', '=', plan_id),
                    ('company_id', '=', company.id)
                ], limit=1)
            if not product and article_id:
                product = self.env['product.product'].search([
                    ('whub_article_id', '=', article_id),
                    ('company_id', '=', company.id)
                ], limit=1)
            
            # Si no se encuentra mapeo, usar un genérico o fallar
            if not product:
                # Buscamos un producto comodín de servicio
                product = self.env['product.product'].search([
                    ('default_code', '=', 'WHUB_SERVICE'),
                    ('company_id', '=', company.id)
                ], limit=1)
                
            if not product:
                # Si no hay producto genérico de servicio, fallamos
                self.env['whub.notice.sync.log'].create({
                    'whub_invoice_id': notice_id,
                    'company_id': company.id,
                    'state': 'error',
                    'error_type': 'product_missing',
                    'error_message': f"No se encontró mapeo para el concepto '{concept}' ni un producto comodín WHUB_SERVICE.",
                    'partner_id': partner.id,
                    'customer_name_wh': customer_name,
                    'raw_json': raw_json,
                })
                return {'success': False, 'error': 'product_missing'}

            order_lines.append((0, 0, {
                'product_id': product.id,
                'name': concept,
                'product_uom_qty': 1.0,
                'price_unit': price,
            }))

        # 3. Crear y confirmar la Orden de Venta
        try:
            with self.env.cr.savepoint():
                sale_order = self.env['sale.order'].create({
                    'partner_id': partner.id,
                    'company_id': company.id,
                    'whub_invoice_id': notice_id,
                    'date_order': notice_data.get('issue_date') or notice_data.get('date') or fields.Datetime.now(),
                    'order_line': order_lines,
                })

                sale_order.action_confirm()

                invoice_id = False
                # whatsapp_enabled se puede verificar o forzar
                sale_order.action_whub_send_whatsapp()

                # Registrar éxito en el Log de Avisos
                self.env['whub.notice.sync.log'].create({
                    'whub_invoice_id': notice_id,
                    'company_id': company.id,
                    'state': 'success',
                    'sale_order_id': sale_order.id,
                    'invoice_id': invoice_id,
                    'partner_id': partner.id,
                    'customer_name_wh': customer_name,
                    'raw_json': raw_json,
                })
                return {'success': True, 'sale_order_id': sale_order.id, 'invoice_id': invoice_id}
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
                'error_message': 'Error de integridad al guardar la orden de venta.'
            }
        except Exception as e:
            self.env['whub.notice.sync.log'].create({
                'whub_invoice_id': notice_id,
                'company_id': company.id,
                'state': 'error',
                'error_type': 'unexpected',
                'error_message': f"Error inesperado: {str(e)}",
                'partner_id': partner.id,
                'customer_name_wh': customer_name,
                'raw_json': raw_json,
            })
            return {'success': False, 'error': 'unexpected'}

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
            
            if response.status_code != 200:
                self._log_error_no_notice(company, 'error_http', f"Middleware respondió con status {response.status_code}")
                raise UserError(f"Error en Middleware: HTTP {response.status_code}")

            try:
                data = response.json()
            except Exception:
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
    def action_sync_payment_notices_by_dates(self, date_from, date_to):
        """
        Sincroniza avisos de cobro usando un rango de fechas específico.
        Similar a action_sync_payment_notices pero con fechas personalizadas.
        """
        company = self.env.company
        url = (company.whub_middleware_url or '').strip().rstrip('/')
        if not url:
            raise UserError("No se ha configurado la URL del Middleware en los Ajustes de WispHub.")

        api_key = (company.whub_api_key or "").strip()
        if not api_key:
            raise UserError("No se ha configurado la API Key de WispHub. Vaya a Ajustes → WispHub.")

        # --- Usar fechas personalizadas ---
        date_from_str = date_from.strftime('%Y-%m-%d')
        date_to_str = (date_to + timedelta(days=1)).strftime('%Y-%m-%d')

        headers = {'Content-Type': 'application/json'}
        base_filters = {
            'date_from': date_from_str,
            'date_to': date_to_str
        }

        _logger.info(
            "WispHub Sync Notices (Fechas Personalizadas): Consultando avisos desde %s hasta %s para compañía %s",
            date_from_str, date_to_str, company.name
        )

        notices, response_keys, first_notice = self._fetch_paginated_notices(
            url=url,
            headers=headers,
            api_key=api_key,
            base_filters=base_filters,
            company=company,
            log_context="WispHub Sync Notices (Fechas Personalizadas)"
        )

        _logger.info(
            "WispHub Sync Notices (Fechas Personalizadas): Recibidos %d avisos. Claves en respuesta: %s",
            len(notices), response_keys
        )
        if first_notice:
            _logger.debug(
                "WispHub Sync Notices (Fechas Personalizadas): Primer aviso: %s",
                json.dumps(first_notice, indent=2)
            )

        # --- Procesar cada aviso ---
        success_count = 0
        error_count = 0
        skipped_count = 0

        for notice in notices:
            notice_id = str(notice.get('id', ''))

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

        # --- Notificación al usuario ---
        msg_parts = []
        if success_count: msg_parts.append(f"✅ {success_count} órdenes creadas")
        if skipped_count: msg_parts.append(f"⏭️ {skipped_count} ya existían")
        if error_count: msg_parts.append(f"❌ {error_count} con errores")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización de Avisos por Fechas',
                'message': '\n'.join(msg_parts) or "No se encontraron avisos en el rango seleccionado.",
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': error_count > 0,
            }
        }

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
        """ Registra errores generales de sincronización global """
        self.env['whub.notice.sync.log'].create({
            'company_id': company.id,
            'state': 'error',
            'error_type': error_type,
            'error_message': message,
        })
