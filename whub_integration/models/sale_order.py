import requests
import json
import logging
from odoo import fields, models, api, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """
    Extensión de sale.order para control anti-duplicados de avisos WispHub
    y gestión de notificaciones WhatsApp vía Middleware.
    """
    _inherit = 'sale.order'

    whub_invoice_id = fields.Char(
        string='ID Aviso WispHub',
        help='ID único del aviso de cobro en WispHub (anti-duplicados)',
        index=True, copy=False
    )

    # --- Datos de referencia del aviso de cobro original en WispHub ---
    # No alteran el cálculo de Odoo (amount_total sigue siendo cantidad x precio
    # de las líneas); se guardan tal cual los reporta WispHub para consulta/auditoría.
    whub_status = fields.Char(string='Estado en WispHub', copy=False)
    whub_due_date = fields.Date(string='Vencimiento WispHub', copy=False)
    whub_payment_date = fields.Date(string='Fecha de Pago WispHub', copy=False)
    whub_amount = fields.Monetary(string='Total WispHub', copy=False)
    whub_sub_total = fields.Monetary(string='Subtotal WispHub', copy=False)
    whub_discount = fields.Monetary(string='Descuento WispHub', copy=False)
    whub_total_taxes = fields.Monetary(string='Impuestos WispHub', copy=False)
    whub_total_collected = fields.Monetary(string='Total Cobrado WispHub', copy=False)
    whub_retention_percentage = fields.Float(string='% Retención WispHub', copy=False)
    whub_total_retentions = fields.Monetary(string='Retenciones WispHub', copy=False)

    _sql_constraints = [
        ('whub_invoice_id_unique',
         'unique(whub_invoice_id)',
         'Ya existe una orden de venta con este ID de aviso de WispHub.')
    ]

    def action_whub_send_whatsapp(self):
        """
        Genera un link de pago de Odoo y solicita a la API Intermedia 
        el envío de una notificación WhatsApp al cliente.
        """
        self.ensure_one()
        company = self.company_id

        # 1. Generar Link de Pago dinámico de Odoo
        # Usamos el wizard nativo para que respete los métodos de pago configurados
        link_wizard = self.env['payment.link.wizard'].with_context(
            active_id=self.id,
            active_model='sale.order',
        ).create({})
        payment_link = link_wizard.link

        # 2. Datos para la API Intermedia
        base_url = (company.whub_middleware_url or '').strip().rstrip('/')
        endpoint = '/api/v1/wisphub/notifications/whatsapp'
        full_url = f"{base_url}{endpoint}"
        
        if not base_url:
            self.message_post(body="⚠️ WispHub: No se pudo enviar WhatsApp. URL del Middleware no configurada.")
            return False

        payload = {
            "auth": {"api_key": company.whub_api_key},
            "notification": {
                "phone": self.partner_id.mobile or self.partner_id.phone or '',
                "whub_customer_id": self.partner_id.whub_customer_id or '',
                "whub_invoice_id": self.whub_invoice_id or '',
                "customer_name": self.partner_id.name or '',
                "order_reference": self.name or '',
                "amount": self.amount_total,
                "payment_link": payment_link
            }
        }

        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(full_url, json=payload, headers=headers, timeout=10)
            
            if response.status_code in (200, 201):
                self.message_post(body=f"Notificación de WhatsApp enviada correctamente al cliente (vía {endpoint}).")
                return True
            else:
                self.message_post(body=f"Fallo al enviar WhatsApp. Respuesta: {response.text}")
                return False
        except Exception as e:
            self.message_post(body=f"Fallo de conexión con la API Intermedia al enviar WhatsApp: {str(e)}")
            return False

    def action_whub_simulate_payment(self):
        """
        Simula el callback de cobro de Pago Móvil / Pasarela:
        1. Confirma la Orden de Venta.
        2. Genera y publica la factura.
        3. Registra el pago en Odoo para dejar la factura en estado Pagado.
        4. Simula la impresión fiscal HKA.
        5. Simula el envío de señal de reactivación de router a WispHub.
        """
        self.ensure_one()
        if not self.whub_invoice_id:
            raise models.ValidationError("Esta orden de venta no está vinculada a ningún aviso de WispHub.")
        if self.state != 'draft':
            raise models.ValidationError("Sólo se puede simular el pago de órdenes en estado borrador.")

        # 1. Confirmar la Orden
        self.action_confirm()

        # 2. Generar Factura
        invoice = self._create_invoices()
        if not invoice:
            raise models.ValidationError("No se pudo generar la factura para esta orden.")

        # 3. Publicar Factura
        invoice.action_post()
        self.message_post(body=f"✅ Factura {invoice.name} generada y publicada automáticamente tras pago móvil simulado.")

        # 4. Registrar Pago Nativamente en Odoo
        journal = self.env['account.journal'].search([('type', 'in', ('bank', 'cash'))], limit=1)
        if not journal:
            raise models.ValidationError("No se encontró ningún diario de Banco o Caja configurado en Odoo para registrar el pago.")

        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'payment_date': fields.Date.context_today(self),
            'journal_id': journal.id,
        })
        payment = payment_register._create_payments()
        self.message_post(body=f"💰 Pago registrado y conciliado con éxito. Factura marcada como Pagada.")

        # 5. Simular Impresión Fiscal HKA
        self.message_post(body="📠 HKA Fiscal: Impresión fiscal del ticket de factura realizada con éxito.")

        # 6. Simular Reactivación de Servicio en WispHub
        base_url = (self.company_id.whub_middleware_url or '').strip().rstrip('/')
        if base_url:
            full_url = f"{base_url}/api/v1/wisphub/reactivate"
            payload = {
                "auth": {"api_key": self.company_id.whub_api_key},
                "reactivate": {
                    "whub_customer_id": self.partner_id.whub_customer_id or '',
                    "whub_invoice_id": self.whub_invoice_id,
                }
            }
            try:
                headers = {'Content-Type': 'application/json'}
                requests.post(full_url, json=payload, headers=headers, timeout=10)
                self.message_post(body="🚀 WispHub: Solicitud de reactivación de servicio enviada al router del cliente.")
            except Exception as e:
                self.message_post(body=f"⚠️ WispHub: No se pudo conectar con el Middleware para reactivar el router: {str(e)}")
        else:
            self.message_post(body="⚠️ WispHub: No se pudo reactivar el router. URL del Middleware no configurada.")

        # Registrar la factura generada en la bitácora
        log = self.env['whub.notice.sync.log'].search([('whub_invoice_id', '=', self.whub_invoice_id)], limit=1)
        if log:
            log.invoice_id = invoice.id

        return True

