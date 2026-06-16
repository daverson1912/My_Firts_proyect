import requests
import logging
from odoo import fields, models, api, _

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """
    Extensión de account.move para gestionar facturación de WispHub,
    fiscalización y cobros corporativos con diferencial cambiario simulado.
    """
    _inherit = 'account.move'

    whub_invoice_id = fields.Char(
        string='ID Aviso WispHub',
        compute='_compute_whub_invoice_id',
        store=True,
        index=True,
        help="ID de aviso de WispHub heredado automáticamente de la Orden de Venta."
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id.whub_invoice_id')
    def _compute_whub_invoice_id(self):
        for move in self:
            whub_id = False
            for line in move.invoice_line_ids:
                for sale_line in line.sale_line_ids:
                    if sale_line.order_id.whub_invoice_id:
                        whub_id = sale_line.order_id.whub_invoice_id
                        break
                if whub_id:
                    break
            move.whub_invoice_id = whub_id

    def action_whub_simulate_company_payment(self):
        """
        Simula el cobro a crédito de una Persona Jurídica:
        1. Detecta un diferencial cambiario (simulado al 10% del total por fluctuación de tasa BCV).
        2. Genera y publica una Nota de Débito por diferencial cambiario en Bolívares.
        3. Registra el pago conjunto de la Factura y de la Nota de Débito en Odoo para cerrarlas.
        4. Simula la impresión fiscal HKA de la Nota de Débito.
        5. Simula el envío de señal de reactivación a WispHub.
        """
        self.ensure_one()
        if not self.whub_invoice_id:
            raise models.ValidationError("Esta factura no está vinculada a ningún aviso de WispHub.")
        if self.state != 'posted':
            raise models.ValidationError("Sólo se puede registrar cobro sobre facturas en estado Publicado.")
        if self.payment_state not in ('not_paid', 'partial'):
            raise models.ValidationError("Esta factura ya ha sido pagada en su totalidad.")

        # 1. Calcular Diferencial Cambiario Simulado (10% del total de la factura original)
        debit_note_amount = self.amount_total * 0.10

        # Obtener una cuenta de ingresos/gastos por diferencial cambiario o de ventas
        account = self.invoice_line_ids[0].account_id
        if self.company_id.income_currency_exchange_account_id:
            account = self.company_id.income_currency_exchange_account_id

        # 2. Crear y Publicar Nota de Débito
        debit_note = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'ref': f"Diferencial Cambiario sobre {self.name} (Tasa BCV Simulación)",
            'invoice_line_ids': [(0, 0, {
                'name': f"Ajuste de diferencial cambiario por tasa del día de pago - Ref: {self.name}",
                'price_unit': debit_note_amount,
                'quantity': 1.0,
                'account_id': account.id,
            })]
        })
        debit_note.action_post()
        self.message_post(body=f"📝 Nota de Débito {debit_note.name} por diferencial cambiario (10% simulado) generada con éxito.")

        # 3. Registrar Pago Nativamente para ambas facturas
        journal = self.env['account.journal'].search([('type', 'in', ('bank', 'cash'))], limit=1)
        if not journal:
            raise models.ValidationError("No se encontró ningún diario de Banco o Caja configurado en Odoo para registrar el pago.")

        # Conciliar ambas facturas juntas
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=[self.id, debit_note.id]
        ).create({
            'payment_date': fields.Date.context_today(self),
            'journal_id': journal.id,
        })
        payment = payment_register._create_payments()
        self.message_post(body=f"💰 Pagos registrados y conciliados para Factura original y Nota de Débito {debit_note.name}. Estado: Totalmente Pagadas.")

        # 4. Simular Impresión HKA de la Nota de Débito
        self.message_post(body=f"📠 HKA Fiscal: Impresión fiscal del ticket de la Nota de Débito {debit_note.name} realizada con éxito.")

        # 5. Simular Reactivación de Servicio en WispHub
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
                self.message_post(body="🚀 WispHub: Solicitud de reactivación de servicio enviada al router del cliente corporativo.")
            except Exception as e:
                self.message_post(body=f"⚠️ WispHub: No se pudo conectar con el Middleware para reactivar el router: {str(e)}")
        else:
            self.message_post(body="⚠️ WispHub: No se pudo reactivar el router. URL del Middleware no configurada.")

        # Actualizar la bitácora
        log = self.env['whub.notice.sync.log'].search([('whub_invoice_id', '=', self.whub_invoice_id)], limit=1)
        if log:
            log.invoice_id = self.id

        return True
