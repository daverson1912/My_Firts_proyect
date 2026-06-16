# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class AccountWhIslr(models.Model):
    """
    Comprobante de Retención de ISLR.
    
    Almacena la información de retenciones de ISLR (Impuesto sobre la Renta)
    efectuadas a proveedores cuando se confirman facturas de compra.
    """
    _name = 'account.wh.islr'
    _description = 'Comprobante de Retención de ISLR'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Número de Comprobante',
        readonly=True,
        copy=False,
        help='Número correlativo del comprobante de ISLR.',
    )

    api_transaction_id = fields.Char(
        string='ID de Transacción API',
        readonly=True,
        copy=False,
        help='ID de referencia con Nest.js para tracking de la transacción.',
    )
    
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Contacto',
        required=True,
        readonly=True,
        tracking=True,
    )
    
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        readonly=True,
        ondelete='cascade',
    )

    type = fields.Selection(
        selection=[
            ('purchase', 'Compra'),
            ('sale', 'Venta'),
        ],
        string='Tipo de Retención',
        required=True,
        default='purchase',
        index=True,
        help='Indica si la retención es de compra (emitida por nosotros) o de venta (recibida del cliente).'
    )
    
    date = fields.Date(
        string='Fecha del Comprobante',
        required=True,
        readonly=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    wh_type = fields.Selection(
        selection=[
            ('invoice', 'Factura'),
            ('refund', 'Nota de Crédito'),
        ],
        string='Tipo de Documento',
        required=True,
        default='invoice',
        readonly=True,
    )

    # ========== CAMPOS MONETARIOS ==========

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        required=True,
        readonly=True,
        store=True,
        help='Siempre en Bolívares (VED/VEF) para cumplimiento fiscal venezolano.',
    )

    amount_total_invoice = fields.Monetary(
        string='Monto Total Factura',
        currency_field='currency_id',
        readonly=True,
        help='Monto total de la factura con ISLR (sin restar retención).',
    )

    amount_taxable_base = fields.Monetary(
        string='Base Imponible',
        currency_field='currency_id',
        readonly=True,
        help='Monto antes de ISLR sobre el cual se aplica la retención.',
    )

    amount_exempt = fields.Monetary(
        string='Monto Exento',
        currency_field='currency_id',
        readonly=True,
    )

    amount_to_pay = fields.Monetary(
        string='Monto a Pagar',
        currency_field='currency_id',
        readonly=True,
        help='Monto neto a pagar en la factura después de todas las retenciones.',
    )

    amount_total_ret = fields.Monetary(
        string='Monto Total Retenido',
        currency_field='currency_id',
        required=True,
        readonly=True,
        tracking=True,
    )

    # ========== CAMPOS RELACIONADOS (Para facilitar búsquedas) ==========

    invoice_number = fields.Char(
        string='Número de Factura',
        compute='_compute_invoice_number',
        store=True,
        readonly=True,
    )

    @api.depends('move_id.name', 'move_id.l10n_ve_supplier_invoice_number', 'type')
    def _compute_invoice_number(self):
        for rec in self:
            if rec.type == 'purchase':
                # En compras usamos el número de factura del proveedor
                rec.invoice_number = rec.move_id.l10n_ve_supplier_invoice_number or rec.move_id.name
            else:
                # En ventas usamos nuestro propio número de factura
                rec.invoice_number = rec.move_id.name

    invoice_date = fields.Date(
        related='move_id.invoice_date',
        string='Fecha de Factura',
        store=True,
        readonly=True,
    )

    partner_vat = fields.Char(
        related='partner_id.vat',
        string='RIF del Proveedor',
        store=True,
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('posted', 'Publicado'),
            ('declared', 'Declarado'),
            ('cancel', 'Anulado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        readonly=True,
        tracking=True,
    )

    # ========== ESTADO DE CORREO ==========

    email_state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('sent', 'Enviado'),
            ('failed', 'Fallido'),
            ('skipped', 'No Aplica'),
        ],
        string='Estado de Correo',
        default='skipped',
        readonly=True,
        tracking=True,
        help='Estado del envío del comprobante por correo electrónico.\n'
             '- Pendiente: En cola para envío automático.\n'
             '- Enviado: Correo enviado exitosamente.\n'
             '- Fallido: Error en el envío (ver detalle).\n'
             '- No Aplica: Sin destinatarios válidos.',
    )

    last_email_at = fields.Datetime(
        string='Último Envío',
        readonly=True,
        help='Fecha y hora del último intento de envío de correo.',
    )

    last_email_error = fields.Text(
        string='Error de Correo',
        readonly=True,
        help='Detalle del último error ocurrido al enviar el correo.',
    )

    email_retry_count = fields.Integer(
        string='Intentos de Envío',
        default=0,
        readonly=True,
        help='Número de intentos realizados para enviar el correo.',
    )

    # ========== CONSTRAINTS DE SEGURIDAD ==========

    @api.ondelete(at_uninstall=False)
    def _unlink_except_declared(self):
        for record in self:
            if record.state == 'declared':
                raise ValidationError(_("No puede eliminar un comprobante que ya ha sido declarado ante el SENIAT."))

    _EMAIL_FIELDS = {'email_state', 'last_email_at', 'last_email_error', 'email_retry_count'}

    def write(self, vals):
        if any(rec.state == 'declared' for rec in self) and 'state' not in vals:
            # Allow writing email-related fields even on declared records
            if not set(vals.keys()).issubset(self._EMAIL_FIELDS):
                raise ValidationError(_("No puede modificar un comprobante que ya ha sido declarado ante el SENIAT."))
        return super(AccountWhIslr, self).write(vals)

    line_ids = fields.One2many(
        comodel_name='account.wh.islr.line',
        inverse_name='islr_id',
        string='Líneas del Comprobante',
        readonly=True,
    )

    def action_process_withholding(self):
        """
        Procesa una única retención de ISLR (Compra o Venta) desde el formulario.
        - Si es Compra: Obtiene correlativo del API.
        - Si es Venta: Abre el asistente para carga manual.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Solo se pueden procesar retenciones en estado Borrador."))
        
        if self.type == 'sale':
            return self.action_open_customer_unifier()
            
        return self.action_unify()

    def action_print_retention(self):
        """
        Imprime el comprobante de retención de ISLR.
        """
        self.ensure_one()
        if not self.name:
            raise ValidationError(_("No puede imprimir un comprobante sin número asignado."))
        
        return self.env.ref('l10n_ve_simplit_fiscal.action_report_wh_islr').report_action(self)

    def action_post(self):
        """
        Marca el comprobante como publicado. 
        """
        for record in self:
            if record.state == 'draft':
                if not record.name:
                    raise ValidationError(_("El comprobante debe tener un número asignado antes de publicarlo."))
                record.write({'state': 'posted'})

    def action_mark_as_declared(self):
        """
        Marca el comprobante como declarado.
        """
        self.write({'state': 'declared'})
        _logger.info(f"[FISCAL-ISLR] Comprobantes declarados: {[r.name for r in self]}")
        return True

    def action_reset_to_draft(self):
        """
        Vuelve el comprobante a estado borrador.
        """
        for record in self:
            if record.state != 'posted':
                raise ValidationError(_("Solo se pueden resetear comprobantes en estado Publicado."))
            record.write({'state': 'draft'})
        _logger.info(f"[FISCAL-ISLR] Comprobantes reseteados a borrador.")
        return True

    def action_cancel(self):
        """
        Anula el comprobante.
        """
        for record in self:
            if record.state == 'declared':
                raise ValidationError(_("No se puede anular un comprobante que ya ha sido declarado."))
            record.write({'state': 'cancel'})

    def action_unify(self):
        """
        Unifica múltiples registros de retención de ISLR bajo un único número de 
        comprobante por proveedor.
        """
        draft_records = self.filtered(lambda r: r.state == 'draft')
        if not draft_records:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin registros procesables'),
                    'message': _('Todos los registros seleccionados ya están procesados o no son válidos.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Validación: No permitir unificar si la factura está en borrador
        for rec in draft_records:
            if rec.move_id.state == 'draft':
                raise ValidationError(_(
                    "Error de Integridad: La factura %s está en estado borrador. "
                    "Debe publicar la factura antes de poder unificar su retención."
                ) % rec.move_id.name)

        partner_groups = {}
        for rec in draft_records:
            if rec.partner_id.id not in partner_groups:
                partner_groups[rec.partner_id.id] = self.env['account.wh.islr']
            partner_groups[rec.partner_id.id] |= rec
            
        today = fields.Date.today()
        
        # Caso A: Re-publicar los que ya tienen número (reversiones)
        for partner_id, records in partner_groups.items():
            with_name = records.filtered(lambda r: r.name)
            if with_name:
                with_name.write({
                    'state': 'posted',
                    'date': today
                })
                # Set email_state based on partner email availability
                for rec in with_name:
                    rec.write({
                        'email_state': 'pending' if rec.partner_id.email else 'skipped',
                        'email_retry_count': 0,
                        'last_email_error': False,
                    })
                _logger.info(f"[FISCAL-ISLR] Re-publicadas {len(with_name)} retenciones (conservando número) para {with_name[0].partner_id.name}")

        # Caso B: Los que NO tienen número → pedir correlativos al API
        providers_to_assign = []
        partners_without_name = {}
        for partner_id, records in partner_groups.items():
            without_name = records.filtered(lambda r: not r.name)
            if without_name:
                partner = without_name[0].partner_id
                providers_to_assign.append({
                    'providerName': (partner.name or '')[:80],
                    'providerOdooId': partner.id,
                })
                partners_without_name[partner.id] = without_name

        if providers_to_assign:
            company = draft_records[0].company_id
            config = self.env['simplitfiscal.config'].search([
                ('company_id', '=', company.id)
            ], limit=1)
            
            if not config:
                raise ValidationError(_("No se encontró configuración fiscal para la empresa %s") % company.name)

            import requests
            from .utils import get_api_url
            api_host = get_api_url()
            api_key = config.ta_api_key if config else False
            
            url = f"{api_host.rstrip('/')}/api/v1/islr-retentions/assign-correlatives"
            headers = {}
            if api_key:
                headers['X-API-Key'] = api_key

            payload = {'providers': providers_to_assign}
            
            _logger.info(f"[FISCAL-ISLR] Solicitando correlativos al API para {len(providers_to_assign)} proveedores")
            _logger.info(f"[FISCAL-ISLR] Payload: {payload}")

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                _logger.info(f"[FISCAL-ISLR] Response Status: {response.status_code}")
                _logger.info(f"[FISCAL-ISLR] Response Body: {response.text}")
                
                try:
                    res_data = response.json()
                except:
                    res_data = {}

                # 1. Validar Status HTTP (200 o 201 son exitosos)
                if response.status_code not in (200, 201):
                    msg = res_data.get('message') or _("Error de comunicación con el Servicio Fiscal (Status: %s).") % response.status_code
                    raise ValidationError(msg)

                # 2. Validar campo error
                if res_data.get('error') != 0:
                    msg = res_data.get('message', _("Error desconocido en el Servicio Fiscal."))
                    raise ValidationError(msg)

                # El éxito total devuelve la data
                res_data = res_data.get('data', {})
            except Exception as e:
                if isinstance(e, ValidationError):
                    raise e
                _logger.error(f"[FISCAL-ISLR] Error al solicitar correlativos: {str(e)}")
                raise ValidationError(
                    _("No se pudo establecer conexión con el Servicio Fiscal. Verifique la configuración de red y el estado del servidor.")
                )

            # Procesar respuesta: asignar correlativo y fecha a cada grupo
            assignments = res_data.get('assignments', [])
            for assignment in assignments:
                p_id = assignment.get('providerOdooId')
                correlative = assignment.get('correlative')
                assign_date = assignment.get('date')
                
                if p_id in partners_without_name and correlative:
                    recs = partners_without_name[p_id]
                    recs.write({
                        'name': correlative,
                        'date': assign_date or today,
                        'state': 'posted',
                    })
                    # Set email_state based on partner email availability
                    for rec in recs:
                        rec.write({
                            'email_state': 'pending' if rec.partner_id.email else 'skipped',
                            'email_retry_count': 0,
                            'last_email_error': False,
                        })
                    config.islr_withholding_sequence_number += 1
                    _logger.info(f"[FISCAL-ISLR] Asignado correlativo {correlative} a {len(recs)} retenciones de proveedor ID={p_id}")

            # Actualizar correlativo display con el siguiente disponible
            next_correlative = res_data.get('nextIslrCorrelative')
            if next_correlative:
                config.islr_withholding_sequence_display = next_correlative
                _logger.info(f"[FISCAL-ISLR] Próximo correlativo ISLR: {next_correlative}")
            
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_retry_email(self):
        """
        Re-encola el comprobante para reenvío de correo.
        """
        for record in self:
            if not record.partner_id.email:
                raise ValidationError(
                    _('El proveedor %s no tiene correo electrónico configurado.') % record.partner_id.name
                )
        self.write({
            'email_state': 'pending',
            'email_retry_count': 0,
            'last_email_error': False,
        })
        return True

    def name_get(self):
        result = []
        for record in self:
            if record.name:
                name = f"{record.name} - {record.partner_id.name}"
            else:
                name = f"Borrador #{record.id} - {record.partner_id.name}"
            result.append((record.id, name))
        return result

    # --- Acciones para Clientes ---
    def action_open_customer_unifier(self):
        """
        Abre el asistente para cargar manualmente el número de comprobante de venta.
        """
        # Filtrar solo registros en borrador y de tipo venta
        draft_records = self.filtered(lambda r: r.state == 'draft' and r.type == 'sale')
        if not draft_records:
            raise UserError(_("No hay retenciones de venta en estado borrador seleccionadas."))

        # Validar que todos los registros sean del mismo cliente
        partners = draft_records.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_("Para cargar un número de comprobante único, todos los registros seleccionados deben pertenecer al mismo Cliente."))

        return {
            'name': _('Cargar Comprobante de Retención ISLR (Venta)'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.wh.islr.customer.unifier',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': partners[0].id,
                'default_wh_islr_ids': [(6, 0, draft_records.ids)],
                'default_date': fields.Date.today(),
            }
        }


class AccountWhIslrLine(models.Model):
    _name = 'account.wh.islr.line'
    _description = 'Detalle de Retención ISLR'

    islr_id = fields.Many2one(
        comodel_name='account.wh.islr',
        string='Comprobante ISLR',
        ondelete='cascade',
        required=True,
    )

    concept_id = fields.Many2one(
        comodel_name='islr.retention.type',
        string='Concepto de Retención',
        required=True,
    )

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
        readonly=True,
        help='Producto al cual se le aplicó este impuesto.',
    )

    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Línea de Factura',
        ondelete='cascade',
        help='Línea de la factura a la cual se le aplicó este impuesto (Auditoría).',
    )

    base_amount = fields.Monetary(
        string='Monto Base (Bruto)',
    )

    subject_amount = fields.Monetary(
        string='Monto Sujeto',
    )

    subject_amount_percentage = fields.Float(
        string='% Base Sujeta',
        help='Porcentaje aplicado a la base para obtener el monto sujeto.',
    )

    subject_amount_display = fields.Char(
        string='Monto Sujeto',
        compute='_compute_subject_amount_display',
    )

    @api.depends('subject_amount', 'subject_amount_percentage', 'currency_id')
    def _compute_subject_amount_display(self):
        for line in self:
            amount = line.subject_amount
            symbol = line.currency_id.symbol or ''
            percentage = line.subject_amount_percentage
            formatted_amount = "{:,.2f}".format(amount).replace(",", "X").replace(".", ",").replace("X", ".")
            line.subject_amount_display = f"{formatted_amount} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    base_retention_amount = fields.Monetary(
        string='Monto Base de Retención',
        help='Monto base (sin sustraendo) calculado por el API.',
    )

    retention_calculation_display = fields.Char(
        string='Calc. Imp. Ret',
        compute='_compute_retention_calculation_display',
    )

    @api.depends('base_retention_amount', 'retention_percentage', 'currency_id')
    def _compute_retention_calculation_display(self):
        for line in self:
            amount = line.base_retention_amount
            symbol = line.currency_id.symbol or ''
            percentage = line.retention_percentage
            formatted_amount = "{:,.2f}".format(amount).replace(",", "X").replace(".", ",").replace("X", ".")
            line.retention_calculation_display = f"{formatted_amount} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    retention_percentage = fields.Float(
        string='% Retención',
    )

    subtrahend = fields.Monetary(
        string='Sustraendo',
    )

    retention_amount = fields.Monetary(
        string='Monto Retenido',
    )

    fiscal_code = fields.Char(
        string='Código Fiscal',
    )

    currency_id = fields.Many2one(
        related='islr_id.currency_id',
        string='Moneda',
        readonly=True,
    )

    invoice_number = fields.Char(
        related='islr_id.invoice_number',
        string='Número de Factura',
        readonly=True,
    )

    invoice_date = fields.Date(
        related='islr_id.invoice_date',
        string='Fecha de Factura',
        readonly=True,
    )


class AccountWhIslrSummary(models.Model):
    """
    Resumen de Comprobantes de Retención de ISLR (SQL View).
    """
    _name = 'account.wh.islr.summary'
    _description = 'Resumen de Comprobantes de Retención ISLR'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _auto = False
    _order = 'date desc, name desc'

    name = fields.Char(string='Número de Comprobante', readonly=True)
    type = fields.Selection([
        ('purchase', 'Compra'),
        ('sale', 'Venta'),
    ], string='Tipo de Retención', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', readonly=True)
    date = fields.Date(string='Fecha', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    
    amount_total_invoice = fields.Monetary(string='Total Factura', currency_field='currency_id', readonly=True)
    amount_taxable_base = fields.Monetary(string='Base Imponible Total', currency_field='currency_id', readonly=True)
    amount_exempt = fields.Monetary(string='Monto Exento Total', currency_field='currency_id', readonly=True)
    amount_total_ret = fields.Monetary(string='Monto Total Retenido', currency_field='currency_id', readonly=True)
    amount_to_pay = fields.Monetary(string='Total a Pagar', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    state = fields.Selection([
        ('posted', 'Publicado'),
        ('declared', 'Declarado'),
    ], string='Estado', readonly=True)

    line_ids = fields.Many2many(
        comodel_name='account.wh.islr',
        string='Facturas Asociadas',
        compute='_compute_line_ids',
    )

    detail_line_ids = fields.Many2many(
        comodel_name='account.wh.islr.line',
        string='Detalle de Líneas',
        compute='_compute_detail_line_ids',
    )

    @api.depends('name', 'partner_id', 'company_id')
    def _compute_line_ids(self):
        WhIslr = self.env['account.wh.islr']
        for record in self:
            records = WhIslr.search([
                ('name', '=', record.name),
                ('type', '=', record.type),
                ('partner_id', '=', record.partner_id.id),
                ('company_id', '=', record.company_id.id),
                ('state', 'in', ['posted', 'declared'])
            ])
            record.line_ids = [(6, 0, records.ids)]

    @api.depends('line_ids')
    def _compute_detail_line_ids(self):
        for record in self:
            # Obtener todas las líneas de detalle de las facturas consolidadas
            lines = record.line_ids.mapped('line_ids')
            record.detail_line_ids = [(6, 0, lines.ids)]

    def init(self):
        from odoo import tools
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    MIN(id) AS id,
                    name,
                    type,
                    partner_id,
                    date,
                    company_id,
                    currency_id,
                    state,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_total_invoice ELSE amount_total_invoice END) AS amount_total_invoice,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_taxable_base ELSE amount_taxable_base END) AS amount_taxable_base,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_exempt ELSE amount_exempt END) AS amount_exempt,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_total_ret ELSE amount_total_ret END) AS amount_total_ret,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_to_pay ELSE amount_to_pay END) AS amount_to_pay
                FROM account_wh_islr
                WHERE name IS NOT NULL AND state IN ('posted', 'declared')
                GROUP BY name, type, partner_id, date, company_id, currency_id, state
            )
        """)

    def action_print_retention(self):
        return self.env.ref('l10n_ve_simplit_fiscal.action_report_wh_islr').report_action(self)

    def action_send_email(self):
        """
        Abre el asistente de envío de correo electrónico con la plantilla de retención de ISLR preseleccionada.
        """
        self.ensure_one()
        template = self.env.ref('l10n_ve_simplit_fiscal.email_template_wh_islr', raise_if_not_found=False)
        
        ctx = {
            'default_model': 'account.wh.islr.summary',
            'default_res_ids': self.ids,
            'default_use_template': bool(template),
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'force_email': True,
            'model_description': _('Comprobante de Retención de ISLR'),
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def message_post_with_template(self, template_id, **kwargs):
        """
        Wrapper para permitir el envío de correos desde este modelo de vista SQL.
        """
        self.ensure_one()
        template = self.env['mail.template'].browse(template_id)
        return template.send_mail(self.id, force_send=True, **kwargs)

    def action_requeue_email(self):
        """
        Re-encola todos los registros del comprobante para reenvío de correo.
        """
        self.ensure_one()
        if not self.partner_id.email:
            raise ValidationError(
                _('El proveedor %s no tiene correo electrónico configurado.') % self.partner_id.name
            )
        # Update all base records for this summary
        for rec in self.line_ids:
            rec.write({
                'email_state': 'pending',
                'email_retry_count': 0,
                'last_email_error': False,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correo Re-encolado'),
                'message': _('El comprobante %s ha sido re-encolado para envío automático.') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }
