import json
import logging
import re
from datetime import datetime

import pytz
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_config_settings import TAFEL_API_URL

_logger = logging.getLogger(__name__)

_API_TIMEOUT = 15

# Matches a single binary arithmetic expression: "field.path OP field.path_or_literal"
_ARITH_RE = re.compile(
    r'^([a-zA-Z_][a-zA-Z0-9_.]*)\s*([-+*/])\s*([a-zA-Z0-9_.]+)$'
)

# Matches template placeholders: <<field.path>> or <<field.path:format_spec>>
_TEMPLATE_RE = re.compile(r'<<([a-zA-Z_][a-zA-Z0-9_.]*)(?::([^>]*))?>>')
_ODOO_REF_PREFIX_RE = re.compile(r'^\[.*?\]\s*')


def _positive_taxes(tax_ids):
    """Return leaf taxes with amount > 0, expanding group taxes to their children."""
    result = tax_ids.browse()
    for t in tax_ids:
        if t.amount_type == 'group':
            result |= t.children_tax_ids.filtered(lambda c: c.amount > 0)
        elif t.amount > 0:
            result |= t
    return result


class TafelConfig(models.Model):
    _name = 'tafel.config'
    _description = 'Configuración Facturación Electrónica'
    _rec_name = 'company_name'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    company_name = fields.Char(string='Nombre de la Empresa', required=True)
    email = fields.Char(string='Correo Electrónico', required=True)
    password = fields.Char(
        string='Contraseña',
        required=True,
        groups='tafel.group_tafel_manager',
    )
    tax_id = fields.Char(string='RIF / ID Fiscal', required=True)
    country_code = fields.Selection(
        [('VE', 'Venezuela')],
        string='País',
        required=True,
        default='VE',
    )
    tenant_id = fields.Char(
        string='UUID de Cuenta',
        readonly=True,
        copy=False,
    )
    plan = fields.Char(
        string='Plan',
        readonly=True,
        copy=False,
    )
    access_token = fields.Char(
        string='Access Token',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )
    refresh_token = fields.Char(
        string='Refresh Token',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )
    registration_date = fields.Datetime(
        string='Fecha de Registro',
        readonly=True,
        copy=False,
    )
    tenant_id_short = fields.Char(
        string='ID de Cuenta',
        compute='_compute_tenant_id_short',
    )
    api_key_id = fields.Char(
        string='ID de API Key',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )
    api_key_raw = fields.Char(
        string='API Key (raw)',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )
    api_key_short = fields.Char(
        string='API Key',
        compute='_compute_api_key_short',
    )
    provider_config_ids = fields.One2many(
        'tafel.provider.config',
        'tafel_config_id',
        string='Proveedor',
    )
    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        string='Proveedor Activo',
        compute='_compute_provider_config_id',
    )
    provider_is_qa = fields.Boolean(
        string='Ambiente QA',
        compute='_compute_provider_config_id',
    )
    fiscal_document_ids = fields.One2many(
        'tafel.fiscal.document',
        'tafel_config_id',
        string='Documentos Fiscales',
    )
    fiscal_document_count = fields.Integer(
        string='Transacciones',
        compute='_compute_fiscal_stats',
    )
    fiscal_document_error_count = fields.Integer(
        string='Errores',
        compute='_compute_fiscal_stats',
    )
    field_map_count = fields.Integer(
        string='Campos Mapeados',
        compute='_compute_field_map_count',
    )
    custom_field_count = fields.Integer(
        string='Info. Adicional',
        compute='_compute_custom_field_count',
    )
    has_transmission_errors = fields.Boolean(
        string='Transmisión bloqueada',
        compute='_compute_has_transmission_errors',
    )

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    def _assert_single_company(self):
        allowed = self.env.context.get('allowed_company_ids', False)
        if allowed and len(allowed) > 1:
            raise UserError(
                _('La configuración de Facturación Electrónica solo puede '
                  'modificarse con una única empresa activa. '
                  'Seleccione una sola empresa e intente de nuevo.')
            )

    def write(self, vals):
        self._assert_single_company()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_single_company()
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

    @api.depends('provider_config_ids', 'provider_config_ids.credential_is_qa')
    def _compute_provider_config_id(self):
        for rec in self:
            provider = rec.provider_config_ids[:1]
            rec.provider_config_id = provider
            rec.provider_is_qa = provider.credential_is_qa if provider else False

    @api.depends('fiscal_document_ids', 'fiscal_document_ids.status')
    def _compute_fiscal_stats(self):
        for rec in self:
            docs = rec.fiscal_document_ids
            rec.fiscal_document_count = len(docs)
            rec.fiscal_document_error_count = len(docs.filtered(
                lambda d: d.status == 'error'
            ))

    @api.depends('fiscal_document_ids.status', 'fiscal_document_ids.disabled')
    def _compute_has_transmission_errors(self):
        for rec in self:
            rec.has_transmission_errors = bool(
                rec.fiscal_document_ids.filtered(
                    lambda d: d.status == 'error' and not d.disabled
                )
            )

    @api.depends('provider_config_ids.field_map_ids')
    def _compute_field_map_count(self):
        for rec in self:
            provider = rec.provider_config_ids[:1]
            rec.field_map_count = len(provider.field_map_ids) if provider else 0

    @api.depends('provider_config_ids.custom_field_ids')
    def _compute_custom_field_count(self):
        for rec in self:
            provider = rec.provider_config_ids[:1]
            rec.custom_field_count = len(provider.custom_field_ids) if provider else 0

    @api.depends('tenant_id')
    def _compute_tenant_id_short(self):
        for rec in self:
            rec.tenant_id_short = ('...' + rec.tenant_id[-6:]) if rec.tenant_id else ''

    @api.depends('api_key_raw')
    def _compute_api_key_short(self):
        for rec in self:
            rec_sudo = rec.sudo()
            rec.api_key_short = (
                '...' + rec_sudo.api_key_raw[-6:]
            ) if rec_sudo.api_key_raw else ''

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_refresh(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_view_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Transacciones',
            'res_model': 'tafel.fiscal.document',
            'view_mode': 'list,form',
            'domain': [('tafel_config_id', '=', self.id)],
            'context': {'default_tafel_config_id': self.id},
        }

    def action_view_errors(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Transacciones con Error',
            'res_model': 'tafel.fiscal.document',
            'view_mode': 'list,form',
            'domain': [('tafel_config_id', '=', self.id), ('status', '=', 'error')],
        }

    def action_field_mapping(self):
        self.ensure_one()
        provider = self.provider_config_ids[:1]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mapeo de Campos — Factura Electrónica',
            'res_model': 'tafel.field.map',
            'view_mode': 'list,form',
            'domain': [('provider_config_id', '=', provider.id)],
            'context': {'default_provider_config_id': provider.id},
        }

    def action_additional_info(self):
        self.ensure_one()
        provider = self.provider_config_ids[:1]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Información Adicional — Factura Electrónica',
            'res_model': 'tafel.custom.field',
            'view_mode': 'list,form',
            'domain': [('provider_config_id', '=', provider.id)],
            'context': {
                'default_provider_config_id': provider.id,
                'search_default_group_source': 1,
            },
        }

    def action_edit_provider(self):
        self.ensure_one()
        provider = self.provider_config_ids[:1]
        if not provider:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': f'Configuración — {provider.provider_name}',
            'res_model': 'tafel.provider.config',
            'res_id': provider.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_configure_provider(self):
        self.ensure_one()
        if self.provider_config_ids:
            raise UserError(_('Ya tiene un proveedor configurado para esta empresa.'))

        wizard_model = self.env['tafel.provider.setup.wizard']
        providers = wizard_model._fetch_providers(self.country_code)

        wizard = wizard_model.create({
            'tafel_config_id': self.id,
            'provider_option_ids': [
                (0, 0, {
                    'provider_id_api': p['id'],
                    'name': p['name'],
                    'config_schema_json': json.dumps(p.get('configSchema', {})),
                    'payment_methods_json': json.dumps(
                        p.get('catalogs', {}).get('paymentMethods', [])
                    ),
                })
                for p in providers
            ],
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tafel.provider.setup.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # HTTP helper
    # -------------------------------------------------------------------------

    def _api_request(self, method, endpoint, *, json=None, params=None, _retry=True):
        """Authenticated HTTP call to tafelapi. Handles token renewal automatically."""
        self.ensure_one()
        self_sudo = self.sudo()
        base = TAFEL_API_URL
        headers = {
            'Authorization': f'Bearer {self_sudo.access_token}',
            'Content-Type': 'application/json',
        }
        if self_sudo.api_key_raw:
            headers['x-api-key'] = self_sudo.api_key_raw
        try:
            response = requests.request(
                method,
                base.rstrip('/') + endpoint,
                json=json,
                params=params,
                headers=headers,
                timeout=_API_TIMEOUT,
            )
        except requests.exceptions.ConnectionError:
            raise UserError(
                _('No se pudo conectar con el servidor de Tafel. '
                  'Verifique la URL de la API en Ajustes.')
            )
        except requests.exceptions.Timeout:
            raise UserError(
                _('El servidor de Tafel no respondió a tiempo (%d s).') % _API_TIMEOUT
            )
        except requests.exceptions.RequestException as exc:
            _logger.exception('Tafel API request error: %s', exc)
            raise UserError(
                _('Error inesperado al contactar el servidor de Tafel: %s') % str(exc)
            )

        if _retry and self._tafel_is_token_expired(response):
            _logger.info('Tafel: token expirado, intentando renovar...')
            self._tafel_renew_tokens()
            return self._api_request(
                method, endpoint, json=json, params=params, _retry=False
            )

        return response

    def _tafel_is_token_expired(self, response):
        if response.status_code == 401:
            return True
        try:
            body = response.json()
            if body.get('error') != 0:
                msg = (body.get('message') or '').lower()
                return 'token' in msg and ('expir' in msg or 'invalid' in msg or 'expirado' in msg)
        except Exception:
            pass
        return False

    def _tafel_renew_tokens(self):
        """Refresh access_token via refresh_token. Falls back to login if expired."""
        self.ensure_one()
        self_sudo = self.sudo()
        base = TAFEL_API_URL.rstrip('/')

        # 1. Intentar con refresh_token
        if self_sudo.refresh_token:
            try:
                resp = requests.post(
                    f'{base}/api/auth/refresh',
                    json={'refreshToken': self_sudo.refresh_token},
                    headers={'Content-Type': 'application/json'},
                    timeout=_API_TIMEOUT,
                )
                body = resp.json()
                if body.get('error') == 0:
                    data = body.get('data', {})
                    self_sudo.write({
                        'access_token': data.get('accessToken') or self_sudo.access_token,
                        'refresh_token': data.get('refreshToken') or self_sudo.refresh_token,
                    })
                    _logger.info('Tafel: token renovado via refresh_token.')
                    return
            except Exception as exc:
                _logger.warning('Tafel: refresh_token falló: %s', exc)

        # 2. Refresh expirado — hacer login con credenciales
        _logger.info('Tafel: refresh_token expirado, iniciando sesión nuevamente...')
        try:
            resp = requests.post(
                f'{base}/api/auth/login',
                json={'email': self.email, 'password': self_sudo.password},
                headers={'Content-Type': 'application/json'},
                timeout=_API_TIMEOUT,
            )
            body = resp.json()
            if body.get('error') == 0:
                data = body.get('data', {})
                self_sudo.write({
                    'access_token': data.get('accessToken') or '',
                    'refresh_token': data.get('refreshToken') or '',
                })
                _logger.info('Tafel: sesión renovada via login.')
                return
            raise UserError(
                _('No se pudo renovar la sesión: %s') % body.get('message', _('Error desconocido.'))
            )
        except UserError:
            raise
        except Exception as exc:
            raise UserError(
                _('No se pudo renovar la sesión con el servidor de Tafel: %s') % str(exc)
            )

    # -------------------------------------------------------------------------
    # Transmission engine
    # -------------------------------------------------------------------------

    @api.model
    def _tafel_cron_transmit(self):
        """Cron: find all pending invoices across all configs and transmit them."""
        for config in self.search([]):
            if not config.provider_config_id:
                continue
            active_journals = config.provider_config_id.journal_config_ids.filtered(
                lambda jc: jc.active
            )
            for journal_config in active_journals:
                config._tafel_process_journal(journal_config)

    def _tafel_process_journal(self, journal_config):
        """Find and transmit all pending invoices for a given journal config."""
        self.ensure_one()

        # Si hay errores activos en este diario, esperar resolución manual
        has_errors = self.env['tafel.fiscal.document'].search_count([
            ('tafel_config_id', '=', self.id),
            ('status', '=', 'error'),
            ('disabled', '=', False),
            ('move_id.journal_id', '=', journal_config.journal_id.id),
        ]) > 0
        if has_errors:
            _logger.info(
                'Tafel: diario "%s" tiene transacciones con error — se omite hasta resolución manual.',
                journal_config.journal_id.name,
            )
            return

        domain = [
            ('journal_id', '=', journal_config.journal_id.id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        if journal_config.start_move_id:
            domain.append(('id', '>=', journal_config.start_move_id.id))

        # Excluir exitosas, con error y deshabilitadas
        excluded_move_ids = self.env['tafel.fiscal.document'].search([
            ('tafel_config_id', '=', self.id),
            '|',
            ('status', 'in', ['success', 'error']),
            ('disabled', '=', True),
        ]).mapped('move_id').ids
        if excluded_move_ids:
            domain.append(('id', 'not in', excluded_move_ids))

        moves = self.env['account.move'].search(domain)
        for move in moves:
            try:
                self._tafel_transmit(move, journal_config)
            except Exception:
                _logger.exception(
                    'Tafel cron: error inesperado al transmitir %s', move.name
                )

    def _tafel_transmit(self, move, journal_config):
        """Transmit an invoice to the fiscal provider. Never raises — errors are recorded."""
        self.ensure_one()

        fiscal_doc = self.env['tafel.fiscal.document'].search([
            ('move_id', '=', move.id),
            ('tafel_config_id', '=', self.id),
        ], limit=1)

        now = fields.Datetime.now()
        if not fiscal_doc:
            fiscal_doc = self.env['tafel.fiscal.document'].create({
                'tafel_config_id': self.id,
                'provider_config_id': self.provider_config_id.id,
                'move_id': move.id,
                'move_name': move.name,
                'partner_name': move.partner_id.name,
                'amount_total': move.amount_total,
                'currency_id': move.currency_id.id,
                'transmission_date': now,
                'status': 'pending',
            })
        else:
            fiscal_doc.write({'transmission_date': now})

        try:
            payload = self._tafel_build_payload(move, journal_config)
        except Exception as exc:
            msg = f'Error al construir el payload: {exc}'
            _logger.exception('Tafel build payload error for %s', move.name)
            fiscal_doc._record_attempt('error', msg, None)
            fiscal_doc.write({'status': 'error', 'status_message': msg})
            return

        fiscal_doc.write({
            'payload_json': json.dumps(payload, ensure_ascii=False, indent=2)
        })

        try:
            response = self._api_request(
                'POST', '/api/fiscal-documents/emit', json=payload
            )
            body = response.json()
        except Exception as exc:
            msg = f'Error de comunicación con la API: {exc}'
            _logger.exception('Tafel API emit error for %s', move.name)
            fiscal_doc._record_attempt('error', msg, None)
            fiscal_doc.write({'status': 'error', 'status_message': msg})
            return

        response_str = json.dumps(body, ensure_ascii=False, indent=2)
        data = body.get('data')
        data_str = json.dumps(data, ensure_ascii=False, indent=2) if data is not None else ''

        if body.get('error') == 0:
            data = data or {}
            provider_response = data.get('providerResponse') or {}
            resultado = provider_response.get('resultado') or {}
            control_number = resultado.get('numeroControl') or data.get('documentNumber') or ''
            url_consulta = resultado.get('urlConsulta') or ''

            fiscal_doc._record_attempt('success', body.get('message', ''), response_str)
            fiscal_doc.write({
                'status': 'success',
                'status_message': body.get('message', ''),
                'fiscal_id': data.get('id') or '',
                'document_number': control_number,
                'pdf_url': url_consulta,
                'fiscal_data_json': response_str,
            })

            if move.exists():
                move_vals = {}
                if control_number:
                    move_vals['l10n_ve_control_number'] = control_number
                if url_consulta:
                    move_vals['digital_document'] = url_consulta
                if move_vals:
                    move.sudo().write(move_vals)
        else:
            msg = body.get('message') or _('Error desconocido del proveedor.')
            fiscal_doc._record_attempt('error', msg, response_str)
            fiscal_doc.write({
                'status': 'error',
                'status_message': msg,
                'fiscal_data_json': response_str,
            })

    def _tafel_build_payload(self, move, journal_config):
        self.ensure_one()
        provider = self.provider_config_id
        field_maps = {fm.api_field_key: fm for fm in provider.field_map_ids}

        def get_val(key, record=move, default=None):
            fm = field_maps.get(key)
            if fm:
                if fm.odoo_expr:
                    val = self._tafel_eval_expr(record, fm.odoo_expr)
                    if val is not None and val is not False and val != '':
                        return val
                if fm.default_value:
                    return fm.default_value
            return default

        match = re.search(r'(\d+)$', move.name or '')
        doc_number = match.group(1) if match else str(move.id)
        doc_type = 'INVOICE' if move.move_type == 'out_invoice' else 'CREDIT_NOTE'

        receiver_email = get_val('receiver.email')
        issuer_email = self.email

        payload = {
            'tenantProviderId': provider.tenant_provider_id,
            'documentType': doc_type,
            'isQa': provider.credential_is_qa,
            'documentNumber': doc_number,
            'issuer': {
                'taxId': self.tax_id or '',
                'name': self.company_name or '',
                'email': [issuer_email] if issuer_email else [],
                'address': get_val('issuer.address') or '',
                'phone': get_val('issuer.phone') or '',
            },
            'receiver': {
                'taxId': get_val('receiver.taxId') or '',
                'name': get_val('receiver.name') or '',
                'address': get_val('receiver.address') or '',
                'phone': get_val('receiver.phone') or '',
                'email': [receiver_email] if receiver_email else [],
            },
            'items': self._tafel_build_items(move, field_maps),
            'totals': self._tafel_build_totals(move, field_maps),
        }

        notes = get_val('notes')
        if notes:
            payload['notes'] = notes

        if journal_config.serie_enabled and journal_config.serie_code:
            payload['series'] = journal_config.serie_code

        if doc_type == 'CREDIT_NOTE' and move.reversed_entry_id:
            orig = move.reversed_entry_id
            orig_match = re.search(r'(\d+)$', orig.name or '')
            payload['relatedExternalId'] = orig_match.group(1) if orig_match else (orig.name or '')
            if orig.invoice_date:
                payload['relatedDocumentDate'] = orig.invoice_date.strftime('%d/%m/%Y')
            payload['relatedDocumentAmount'] = orig.amount_total
            orig_journal_config = self.env['tafel.journal.config'].search([
                ('provider_config_id', '=', provider.id),
                ('journal_id', '=', orig.journal_id.id),
                ('active', '=', True),
            ], limit=1)
            payload['relatedDocumentSeries'] = (
                orig_journal_config.serie_code
                if orig_journal_config and orig_journal_config.serie_enabled
                else ''
            )
            adjustment = (
                get_val('adjustmentComment')
                or (move.narration and str(move.narration).strip())
                or move.ref
                or 'Nota de Crédito'
            )
            payload['adjustmentComment'] = adjustment

        if move.invoice_date_due:
            payload['dueDate'] = move.invoice_date_due.strftime('%d/%m/%Y')

        payload['paymentType'] = 'Credito' if move.amount_residual > 0.001 else 'Contado'

        vendor = {}
        for key in ('code', 'name', 'cashierNumber'):
            v = get_val(f'vendor.{key}')
            if v:
                vendor[key] = str(v)
        if vendor:
            payload['vendor'] = vendor

        additional_info = self._tafel_build_additional_info(move, 'move')
        if additional_info:
            payload['additionalInfo'] = additional_info

        tz_name = self.env.company.partner_id.tz or 'America/Caracas'
        local_now = datetime.now(pytz.utc).astimezone(pytz.timezone(tz_name))
        payload['emissionTime'] = local_now.strftime('%H:%M:%S')

        return payload

    @staticmethod
    def _to_float(val, fallback):
        if val is None or val is False or val == '':
            try:
                return float(fallback)
            except (TypeError, ValueError):
                return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            try:
                return float(fallback)
            except (TypeError, ValueError):
                return 0.0

    def _tafel_build_items(self, move, field_maps):
        items = []
        product_lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        for line in product_lines:
            def get_line_val(key, default=None, _line=line):
                fm = field_maps.get(key)
                if fm:
                    if fm.odoo_expr:
                        val = self._tafel_eval_expr(_line, fm.odoo_expr)
                        if val is not None and val is not False and val != '':
                            return val
                    if fm.default_value:
                        return fm.default_value
                return default

            positive_taxes = _positive_taxes(line.tax_ids)
            tax_rate = sum(positive_taxes.mapped('amount'))
            tax_amount = round(line.price_subtotal * tax_rate / 100.0, 2)

            detailed_type = get_line_val('items[].goodOrService')
            good_or_service = '2' if str(detailed_type) == 'service' else '1'

            raw_uom = get_line_val('items[].unitMeasure') or ''
            fm_uom = field_maps.get('items[].unitMeasure')
            if not raw_uom or len(str(raw_uom)) > 5:
                unit_measure = (fm_uom.default_value if fm_uom else None) or 'UND'
            else:
                unit_measure = str(raw_uom)

            line_subtotal = self._to_float(get_line_val('items[].subtotal'), line.price_subtotal)
            line_tax_amount = self._to_float(get_line_val('items[].taxAmount'), tax_amount)

            # price_unit en Odoo es ANTES del descuento; discount es porcentaje (0-100)
            price_before_discount = self._to_float(
                get_line_val('items[].unitPrice'), line.price_unit
            )
            discount_amount_unit = round(price_before_discount * (line.discount / 100.0), 2)
            effective_unit_price = round(price_before_discount - discount_amount_unit, 2)

            item = {
                'description': _ODOO_REF_PREFIX_RE.sub('', str(get_line_val('items[].description', line.name or '') or '')).strip(),
                'quantity': line.quantity,
                'unitPrice': effective_unit_price,
                'discount': round(price_before_discount * line.quantity * (line.discount / 100.0), 2),
                'taxRate': tax_rate,
                'taxAmount': line_tax_amount,
                'subtotal': line_subtotal,
                'goodOrService': good_or_service,
                'unitMeasure': unit_measure,
                'discountedUnitPrice': discount_amount_unit,
                'priceBeforeDiscount': price_before_discount,
            }

            ciiu = get_line_val('items[].ciiu')
            if ciiu:
                item['ciiu'] = str(ciiu)

            sku = get_line_val('items[].sku')
            if sku:
                item['sku'] = str(sku)

            bonus_amount = get_line_val('items[].bonusAmount')
            try:
                bonus_float = float(bonus_amount) if bonus_amount else 0.0
            except (ValueError, TypeError):
                bonus_float = 0.0
            if bonus_float:
                item['bonusAmount'] = bonus_float
                bonus_desc = get_line_val('items[].bonusDescription')
                if bonus_desc:
                    item['bonusDescription'] = str(bonus_desc)

            surcharge = get_line_val('items[].surchargeAmount')
            try:
                surcharge_float = float(surcharge) if surcharge else 0.0
            except (ValueError, TypeError):
                surcharge_float = 0.0
            if surcharge_float:
                item['surchargeAmount'] = surcharge_float

            item_info = self._tafel_build_additional_info(line, 'line')
            if item_info:
                item['additionalInfo'] = item_info

            items.append(item)
        return items

    def _tafel_build_additional_info(self, record, source_model):
        result = []
        for cf in self.provider_config_id.custom_field_ids.filtered(
            lambda f: f.source_model == source_model
        ):
            if cf.value_type == 'template' and cf.template_text:
                rendered = self._tafel_render_template(record, cf.template_text)
                if rendered:
                    result.append({'field': cf.name, 'value': rendered})
            elif cf.value_type == 'auto' and cf.odoo_expr:
                val = self._tafel_eval_expr(record, cf.odoo_expr)
                if val is not None and val is not False and val != '':
                    result.append({'field': cf.name, 'value': str(val)})
            else:
                val = cf.default_value or None
                if val is not None and val is not False and val != '':
                    result.append({'field': cf.name, 'value': str(val)})
        return result

    def _tafel_render_template(self, record, template_text):
        """Render a template string replacing <<field>> and <<field:fmt>> placeholders.

        If the template is a JSON object, each string value is interpolated and the
        result is re-serialized as a JSON string (the whole JSON becomes the 'value').
        """
        from datetime import date, datetime

        def _replace(m):
            field_path = m.group(1)
            fmt = m.group(2)
            val = self._tafel_eval_expr(record, field_path)
            if val is None or val is False:
                return ''
            if fmt:
                try:
                    if isinstance(val, (datetime, date)):
                        return val.strftime(fmt)
                    return format(val, fmt)
                except Exception:
                    pass
            return str(val)

        try:
            data = json.loads(template_text)
            if isinstance(data, dict):
                rendered = {
                    key: _TEMPLATE_RE.sub(_replace, val) if isinstance(val, str) else val
                    for key, val in data.items()
                }
                return json.dumps(rendered, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            pass

        return _TEMPLATE_RE.sub(_replace, template_text)

    def _tafel_build_totals(self, move, field_maps):
        def get_val(key, default=None):
            fm = field_maps.get(key)
            if fm:
                if fm.odoo_expr:
                    val = self._tafel_eval_expr(move, fm.odoo_expr)
                    if val is not None and val is not False and val != '':
                        return val
                if fm.default_value:
                    return fm.default_value
            return default

        product_lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        total_discount = sum(
            l.price_unit * l.quantity * (l.discount / 100.0) for l in product_lines
        )
        taxable_lines = product_lines.filtered(
            lambda l: bool(_positive_taxes(l.tax_ids))
        )
        exempt_lines = product_lines.filtered(
            lambda l: not bool(_positive_taxes(l.tax_ids))
        )
        tax_base = sum(l.price_subtotal for l in taxable_lines)
        exempt_amount = sum(l.price_subtotal for l in exempt_lines)

        exchange_rate = get_val('totals.exchangeRate')
        if not exchange_rate and move.currency_id != move.company_id.currency_id:
            exchange_rate = getattr(move, 'invoice_currency_rate', None)
        try:
            exchange_rate_float = float(exchange_rate) if exchange_rate else None
        except (ValueError, TypeError):
            exchange_rate_float = None

        # Gross total uses only positive taxes (IVA), expanding groups, excluding retentions
        positive_tax_total = sum(
            round(
                l.price_subtotal
                * sum(_positive_taxes(l.tax_ids).mapped('amount'))
                / 100.0,
                2,
            )
            for l in product_lines
        )
        gross_total = round(move.amount_untaxed + positive_tax_total, 2)

        totals = {
            'subtotal': move.amount_untaxed,
            'discount': total_discount,
            'total': gross_total,
            'currency': str(get_val('totals.currency', move.currency_id.name or 'VES')),
            'paymentMethods': self._tafel_build_payment_methods(move, exchange_rate_float, gross_total=gross_total),
            'exchangeRateOperator': str(get_val('totals.exchangeRateOperator', '/')),
        }

        if exchange_rate_float:
            totals['exchangeRate'] = exchange_rate_float

        ref_currency = get_val('totals.referenceCurrency')
        if ref_currency:
            totals['referenceCurrency'] = str(ref_currency)

        return totals

    def _tafel_build_payment_methods(self, move, exchange_rate=None, gross_total=None):
        provider = self.provider_config_id
        payment_map = {
            m.journal_id.id: m.provider_payment_method_id
            for m in provider.payment_method_map_ids
        }
        pm = payment_map.get(move.journal_id.id)
        if not pm and provider.payment_method_map_ids:
            pm = provider.payment_method_map_ids[0].provider_payment_method_id

        invoice_date = move.invoice_date
        date_str = invoice_date.strftime('%d/%m/%Y') if invoice_date else ''
        currency = move.currency_id.name or 'VES'
        needs_rate = currency not in ('VES', 'VED')

        def _entry(method, amount, description):
            e = {
                'method': method,
                'amount': amount,
                'currency': currency,
                'date': date_str,
                'description': description,
            }
            if needs_rate and exchange_rate:
                e['exchangeRate'] = exchange_rate
            return e

        result = []
        # actual_paid = cash/bank reconciled (retentions as negative taxes = 0)
        actual_paid = max(0.0, round(move.amount_total - move.amount_residual, 2))
        base_total = gross_total if gross_total is not None else move.amount_total
        paid_amount = actual_paid
        residual = max(0.0, round(base_total - paid_amount, 2))

        if paid_amount > 0.001:
            result.append(_entry(
                pm.code if pm else '01',
                paid_amount,
                pm.name if pm else '',
            ))

        if residual > 0.001:
            result.append(_entry('99', residual, 'Crédito'))

        if not result:
            result.append(_entry(
                pm.code if pm else '01',
                move.amount_total,
                pm.name if pm else '',
            ))

        return result

    def _tafel_eval_expr(self, record, expr):
        """Evaluate a dot-notation path or a binary arithmetic expression on a record."""
        if not expr:
            return None
        expr = expr.strip()

        m = _ARITH_RE.match(expr)
        if m:
            lhs, op, rhs = m.group(1), m.group(2), m.group(3)
            left = self._tafel_resolve_path(record, lhs)
            right = self._tafel_resolve_path(record, rhs)
            _logger.warning('TAFEL ARITH: %r [%s] %r -> left=%r right=%r', lhs, op, rhs, left, right)
            try:
                lv = float(left if left is not None else 0)
                rv = float(right if right is not None else 0)
                if op == '*':
                    return round(lv * rv, 6)
                if op == '/':
                    return round(lv / rv, 6) if rv else None
                if op == '+':
                    return round(lv + rv, 6)
                if op == '-':
                    return round(lv - rv, 6)
            except (ValueError, TypeError, ZeroDivisionError):
                if op == '+':
                    l_str = str(left) if left else ''
                    r_str = str(right) if right else ''
                    return ', '.join(p for p in [l_str, r_str] if p) or None
        else:
            _logger.warning('TAFEL NO MATCH for: %r', expr)

        return self._tafel_resolve_path(record, expr)

    def _tafel_resolve_path(self, record, expr):
        """Resolve a dot-notation field path or a numeric literal against a record."""
        try:
            return float(expr)
        except (ValueError, TypeError):
            pass
        try:
            value = record
            for part in expr.split('.'):
                if not value:
                    return None
                value = getattr(value, part, None)
            if hasattr(value, '_name'):
                return str(value) if value else None
            if value is False:
                return None
            return value
        except Exception:
            return None
