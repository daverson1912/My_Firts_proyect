# Flujo de Notificaciones WhatsApp (Odoo -> API Intermedia -> WispHub)

Este documento describe la arquitectura y el funcionamiento técnico de las notificaciones de pago enviadas a los clientes.

---

## 1. Arquitectura del Flujo
El proceso de notificación está diseñado para ser desacoplado y delegar la mensajería a WispHub a través de la infraestructura existente.

1.  **Odoo**: Detecta la creación de una Orden de Venta, genera un `payment_link` nativo y dispara la petición.
2.  **API Intermedia**: Recibe los datos de Odoo, valida la autenticación y reenvía la instrucción a WispHub.
3.  **WispHub**: Procesa el mensaje y lo entrega al cliente final vía WhatsApp.

---

## 2. Especificación Técnica (Endpoint)

**URL de Destino**: `{middleware_url}/api/v1/notifications/whatsapp`  
**Método**: `POST`  
**Headers**: `Content-Type: application/json`

### Estructura del Payload (JSON)
```json
{
  "auth": {
    "api_key": "string"
  },
  "notification": {
    "phone": "string",
    "whub_customer_id": "string",
    "customer_name": "string",
    "order_reference": "string",
    "amount": float,
    "message": "string",
    "payment_link": "string"
  }
}
```

---

## 3. Configuración Dinámica en Odoo

Los parámetros se gestionan desde **Ajustes > WispHub Integration**:

*   **Habilitar WhatsApp**: Activa el envío automático tras cada sincronización exitosa.
*   **Ruta Endpoint WhatsApp**: Permite definir dinámicamente a qué ruta del Middleware se enviará el POST (por defecto: `/api/v1/notifications/whatsapp`).
*   **Plantilla de Mensaje**: Permite personalizar el texto usando marcadores dinámicos que se evalúan de forma segura:
    *   `{cliente}`: Nombre del cliente.
    *   `{orden}`: Referencia de la orden (ej: S0001).
    *   `{monto}`: Total a pagar con símbolo de moneda.
    *   `{link}`: URL única del portal de pagos de Odoo.

---

## 4. Auditoría y Registro (Chatter)

Para evitar trabajar a ciegas, el sistema registra cada evento en el **Chatter** (Historial de Notas) de la Orden de Venta:
*   ✅ **Éxito**: Muestra a través de qué endpoint se envió el mensaje.
*   ❌ **Error de API**: Registra la respuesta exacta de la API Intermedia.
*   ⚠️ **Error Interno**: Advierte si falta configuración en el Middleware.

---

## 5. Funcionamiento Automático vs Manual

*   **Automático**: El motor de sincronización (`whub.notice.sync.engine`) invoca el envío inmediatamente después de confirmar la Orden de Venta.
*   **Manual**: Se ha habilitado un botón en el formulario de la Orden de Venta para re-intentar el envío a demanda.

---
**Antigravity AI** | *Advanced Agentic Coding*
