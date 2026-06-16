# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountWhIva(models.Model):
    """
    Comprobante de Retención de IVA.
    
    Almacena la información de retenciones de IVA efectuadas a proveedores
    cuando se confirman facturas de compra. El comprobante se crea en estado
    'draft' y será procesado posteriormente vía interfaz unificador para
    obtener numeración desde API Nest.js.
    """
    _name = 'account.wh.iva'
    _description = 'Comprobante de Retención de IVA'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    
    # ========== CAMPOS BÁSICOS ==========
    
    name = fields.Char(
        string='Número de Comprobante',
        readonly=True,
        copy=False,
        help='Número correlativo del comprobante. Se llena con la respuesta del API.',
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
        help='Contacto asociado a la retención.',
    )
    
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        readonly=True,
        ondelete='cascade',
        help='Factura que generó esta retención.',
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
        help='Fecha en que se procesa el comprobante de retención.',
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
        help='Indica si la retención proviene de una factura o una nota de crédito.'
    )

    parent_wh_iva_id = fields.Many2one(
        'account.wh.iva',
        string='Retención de Origen',
        readonly=True,
        help='Comprobante de retención original al que hace referencia esta nota de crédito.',
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
        default=lambda self: self.env.company.currency_id,
    )

    amount_base = fields.Monetary(
        string='Impuesto Base (IVA)',
        currency_field='currency_id',
        readonly=True,
        help='Monto total del IVA de la factura sobre el cual se calcula la retención.',
    )

    control_number = fields.Char(
        string='Número de Control',
        readonly=True,
        help='Número de control de la factura asociado.',
    )

    debit_note_number = fields.Char(
        string='Número Nota de Débito',
        readonly=True,
    )

    credit_note_number = fields.Char(
        string='Número Nota de Crédito',
        readonly=True,
    )

    operation_type = fields.Selection(
        selection=[
            ('01-REG', 'Registro (01-REG)'),
            ('02-COMP', 'Complemento (02-COMP)'),
            ('03-ANNUL', 'Anulación (03-ANNUL)'),
        ],
        string='Clase de Operación',
        readonly=True,
    )

    affected_invoice_number = fields.Char(
        string='Número de Factura Afectada',
        readonly=True,
        help='En caso de notas de débito/crédito, el número de la factura original.',
    )

    amount_total_signed = fields.Monetary(
        string='Monto Total (Neto)',
        currency_field='currency_id',
        readonly=True,
        help='Monto total de la factura restando la retención.',
    )

    amount_total_invoice = fields.Monetary(
        string='Monto Total Factura',
        currency_field='currency_id',
        readonly=True,
        help='Monto total de la factura con IVA (sin restar retención).',
    )

    amount_exempt = fields.Monetary(
        string='Monto Exento',
        currency_field='currency_id',
        readonly=True,
    )

    supplier_invoice_number = fields.Char(
        string='Nro Factura Proveedor',
        readonly=True,
        help='Número de la factura física del proveedor.',
    )

    amount_taxable_base = fields.Monetary(
        string='Base Imponible',
        currency_field='currency_id',
        readonly=True,
        help='Monto antes de IVA sobre el cual se aplica la alícuota.',
    )

    tax_aliquot = fields.Float(
        string='% Alícuota',
        digits=(16, 2),
        readonly=True,
    )

    amount_vat_tax = fields.Monetary(
        string='Impuesto Causado',
        currency_field='currency_id',
        readonly=True,
    )

    retention_percentage = fields.Float(
        string='% Retenido',
        digits=(16, 2),
        readonly=True,
    )
    
    amount_total_ret = fields.Monetary(
        string='Monto Total Retenido',
        currency_field='currency_id',
        required=True,
        readonly=True,
        tracking=True,
        help='Monto total de IVA retenido en esta factura.',
    )
    
    # ========== ESTADO ==========
    
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
        help='Estado del comprobante:\n'
             '- Borrador: Creado automáticamente, pendiente de procesamiento.\n'
             '- Publicado: Ya fue procesado vía API y tiene número asignado.\n'
             '- Declarado: El comprobante ha sido declarado ante el SENIAT.\n'
             '- Anulado: El comprobante ha sido anulado.'
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

    _EMAIL_FIELDS = {'email_state', 'last_email_at', 'last_email_error', 'email_retry_count'}

    @api.ondelete(at_uninstall=False)
    def _unlink_except_declared(self):
        for record in self:
            if record.state == 'declared':
                raise ValidationError(_("No puede eliminar un comprobante que ya ha sido declarado ante el SENIAT."))

    def write(self, vals):
        if any(rec.state == 'declared' for rec in self) and 'state' not in vals:
            # Allow writing email-related fields even on declared records
            if not set(vals.keys()).issubset(self._EMAIL_FIELDS):
                raise ValidationError(_("No puede modificar un comprobante que ya ha sido declarado ante el SENIAT."))
        return super(AccountWhIva, self).write(vals)
    
    # ========== CAMPOS RELACIONADOS (Para facilitar búsquedas) ==========
    
    invoice_number = fields.Char(
        related='move_id.name',
        string='Número de Factura',
        store=True,
        readonly=True,
    )
    
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
    
    # ========== MÉTODOS ==========
    
    @api.model
    def create(self, vals):
        """
        Override para logging de creación.
        """
        record = super().create(vals)
        _logger.info(
            f"[FISCAL] Comprobante de retención creado: "
            f"ID={record.id}, Proveedor={record.partner_id.name}, "
            f"Monto={record.amount_total_ret}, Factura={record.invoice_number}"
        )
        return record
    
    @api.constrains('amount_total_ret')
    def _check_amount_total_ret(self):
        """
        Valida que el monto total retenido sea positivo.
        """
        for record in self:
            if record.amount_total_ret <= 0:
                raise ValidationError(
                    _('El monto total retenido debe ser mayor a cero. '
                      'Monto actual: %s') % record.amount_total_ret
                )
    
    @api.constrains('move_id')
    def _check_unique_move(self):
        """
        Valida que no existan múltiples comprobantes para la misma factura.
        """
        for record in self:
            existing = self.search([
                ('move_id', '=', record.move_id.id),
                ('id', '!=', record.id),
                ('state', 'not in', ['cancel', 'declared']), # Updated to exclude 'declared' and 'cancel'
            ], limit=1)
            if existing:
                raise ValidationError(
                    _('Ya existe un comprobante de retención para la factura %s. '
                      'Comprobante existente: ID=%s') % (
                        record.invoice_number, existing.id
                    )
                )
    
    def action_process_withholding(self):
        """
        Procesa una única retención de IVA (Compra o Venta) desde el formulario.
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
        Imprime el comprobante de retención.
        Busca el resumen correspondiente para usar el reporte unificado.
        """
        self.ensure_one()
        if not self.name:
            raise ValidationError(_("No puede imprimir un comprobante sin número asignado."))
        
        # El reporte está diseñado para el modelo de resumen (summary)
        # pero podemos pasarle el recordset de la retención individual
        return self.env.ref('l10n_ve_simplit_fiscal.action_report_wh_iva').report_action(self)

    def action_mark_as_posted(self):
        """
        Marca el comprobante como publicado.
        Este método será llamado desde la interfaz unificador después de
        procesar el comprobante vía API.
        """
        for record in self:
            if record.state != 'draft':
                raise ValidationError(
                    _('Solo se pueden publicar comprobantes en estado Borrador.')
                )
            
            if not record.name:
                raise ValidationError(
                    _('El comprobante debe tener un número asignado antes de publicarlo.')
                )
        
        self.write({'state': 'posted'})
        _logger.info(f"[FISCAL] Comprobantes publicados: {[r.name for r in self]}")
        return True
    
    def action_reset_to_draft(self):
        """
        Vuelve el comprobante a estado borrador.
        Útil para correcciones.
        """
        self.ensure_one()
        if self.state != 'posted': # Changed from 'done'
            raise ValidationError(
                _('Solo se pueden resetear comprobantes en estado Publicado.') # Changed from 'Procesado'
            )
        
        self.write({'state': 'draft'})
        _logger.info(
            f"[FISCAL] Comprobante reseteado a borrador: "
            f"Número={self.name}, ID={self.id}"
        )
        return True

    def action_mark_as_declared(self):
        """
        Marca el comprobante como declarado.
        """
        self.write({'state': 'declared'})
        _logger.info(f"[FISCAL] Comprobantes declarados: {[r.name for r in self]}")
        return True

    def action_cancel(self):
        """
        Anula el comprobante.
        """
        for record in self:
            if record.state == 'declared':
                raise ValidationError(
                    _('No se puede anular un comprobante que ya ha sido declarado (Factura %s).') % record.invoice_number
                )
        self.write({'state': 'cancel'})
        _logger.info(f"[FISCAL] Comprobantes anulados: {[r.id for r in self]}")
        return True

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
        """
        Nombre de display personalizado.
        """
        result = []
        for record in self:
            if record.name:
                name = f"{record.name} - {record.partner_id.name}"
            else:
                name = f"Borrador #{record.id} - {record.partner_id.name}"
            result.append((record.id, name))
        return result
    
    # ========== ACCIONES ==========
    
    def action_unify(self):
        """
        Unifica múltiples registros de retención de IVA bajo un único número de 
        comprobante por proveedor.
        """
        # Filtrar solo registros en borrador
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

        # Agrupar por proveedor
        partner_groups = {}
        for rec in draft_records:
            if rec.partner_id.id not in partner_groups:
                partner_groups[rec.partner_id.id] = self.env['account.wh.iva']
            partner_groups[rec.partner_id.id] |= rec
            
        today = fields.Date.today()
        
        # Separar registros con y sin nombre para todos los proveedores
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
                _logger.info(f"[FISCAL-IVA] Re-publicadas {len(with_name)} retenciones (conservando número) para {with_name[0].partner_id.name}")

        # Caso B: Los que NO tienen número → pedir correlativos al API
        providers_to_assign = []
        partners_without_name = {}  # partner_id -> records
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
            # Obtener config y API Key
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
            
            url = f"{api_host.rstrip('/')}/api/v1/iva-retentions/assign-correlatives"
            headers = {}
            if api_key:
                headers['X-API-Key'] = api_key

            payload = {'providers': providers_to_assign}
            
            _logger.info(f"[FISCAL-IVA] Solicitando correlativos al API para {len(providers_to_assign)} proveedores")
            _logger.info(f"[FISCAL-IVA] Payload: {payload}")

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                _logger.info(f"[FISCAL-IVA] Response Status: {response.status_code}")
                _logger.info(f"[FISCAL-IVA] Response Body: {response.text}")
                
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
                _logger.error(f"[FISCAL-IVA] Error al solicitar correlativos: {str(e)}")
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
                    config.withholding_sequence_number += 1
                    _logger.info(f"[FISCAL-IVA] Asignado correlativo {correlative} a {len(recs)} retenciones de proveedor ID={p_id}")

            # Actualizar correlativo display con el siguiente disponible
            next_correlative = res_data.get('nextIvaCorrelative')
            if next_correlative:
                config.withholding_sequence_display = next_correlative
                _logger.info(f"[FISCAL-IVA] Próximo correlativo IVA: {next_correlative}")
            
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


    # --- Acciones para Clientes ---
    def action_open_customer_unifier(self):
        """
        Abre el asistente para cargar manualmente el número de comprobante de venta.
        """
        # Filtrar solo registros en borrador
        draft_records = self.filtered(lambda r: r.state == 'draft' and r.type == 'sale')
        if not draft_records:
            raise UserError(_("No hay retenciones de venta en estado borrador seleccionadas."))

        # Validar que todos los registros sean del mismo cliente
        partners = draft_records.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_("Para cargar un número de comprobante único, todos los registros seleccionados deben pertenecer al mismo Cliente."))

        return {
            'name': _('Cargar Comprobante de Retención (Venta)'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.wh.iva.customer.unifier',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': partners[0].id,
                'default_wh_iva_ids': [(6, 0, draft_records.ids)],
                'default_date': fields.Date.today(),
            }
        }


class AccountWhIvaSummary(models.Model):
    """
    Modelo de solo lectura basado en una vista SQL para agrupar los registros
    de retención por número de comprobante.
    """
    _name = 'account.wh.iva.summary'
    _description = 'Resumen de Comprobantes de Retención'
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
    
    amount_base = fields.Monetary(string='Monto IVA Total', currency_field='currency_id', readonly=True)
    amount_taxable_base = fields.Monetary(string='Base Imponible Total', currency_field='currency_id', readonly=True)
    amount_exempt = fields.Monetary(string='Monto Exento Total', currency_field='currency_id', readonly=True)
    amount_total_signed = fields.Monetary(string='Monto Neto Total', currency_field='currency_id', readonly=True)
    amount_total_invoice = fields.Monetary(string='Monto Factura Total', currency_field='currency_id', readonly=True)
    amount_total_ret = fields.Monetary(string='Monto Total Retenido', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    state = fields.Selection([
        ('posted', 'Publicado'),
        ('declared', 'Declarado'),
    ], string='Estado', readonly=True)

    line_ids = fields.Many2many(
        comodel_name='account.wh.iva',
        string='Facturas Asociadas',
        compute='_compute_line_ids',
    )

    def _compute_line_ids(self):
        """
        Busca todos los registros individuales que componen este resumen.
        """
        WhIva = self.env['account.wh.iva']
        for record in self:
            record.line_ids = WhIva.search([
                ('name', '=', record.name),
                ('type', '=', record.type),
                ('partner_id', '=', record.partner_id.id),
                ('company_id', '=', record.company_id.id),
                ('state', 'in', ['posted', 'declared'])
            ])

    def init(self):
        """
        Crea la vista SQL para agrupar las retenciones.
        """
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
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_base ELSE amount_base END) AS amount_base,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_taxable_base ELSE amount_taxable_base END) AS amount_taxable_base,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_exempt ELSE amount_exempt END) AS amount_exempt,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_total_signed ELSE amount_total_signed END) AS amount_total_signed,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_total_invoice ELSE amount_total_invoice END) AS amount_total_invoice,
                    SUM(CASE WHEN wh_type = 'refund' THEN -amount_total_ret ELSE amount_total_ret END) AS amount_total_ret
                FROM account_wh_iva
                WHERE name IS NOT NULL AND state IN ('posted', 'declared')
                GROUP BY name, type, partner_id, date, company_id, currency_id, state
            )
        """)

    def action_print_retention(self):
        """
        Método para la impresión del comprobante de retención.
        Invoca la acción del reporte QWeb.
        """
        return self.env.ref('l10n_ve_simplit_fiscal.action_report_wh_iva').report_action(self)

    def message_post_with_template(self, template_id, **kwargs):
        """
        Wrapper para permitir el envío de correos desde este modelo de vista SQL.
        """
        self.ensure_one()
        template = self.env['mail.template'].browse(template_id)
        return template.send_mail(self.id, force_send=True, **kwargs)

    def action_send_email(self):
        """
        Abre el asistente de envío de correo electrónico con la plantilla de retención preseleccionada.
        """
        self.ensure_one()
        template = self.env.ref('l10n_ve_simplit_fiscal.email_template_wh_iva', raise_if_not_found=False)
        
        ctx = {
            'default_model': 'account.wh.iva.summary',
            'default_res_ids': self.ids,
            'default_use_template': bool(template),
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'force_email': True,
            'model_description': _('Comprobante de Retención de IVA'),
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
