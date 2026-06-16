# l10n_ve_ta_multicurrency — Venezuelan Multicurrency Module

> **Versión:** 18.0.1.0.0 | **Licencia:** LGPL-3  
> **Dependencias:** `account`, `sale_management`

Habilita el entorno bimonetario USD/Bs en Odoo 18. Crea una capa fiscal paralela en Bolívares (VES) para el **Catálogo de Productos, Presupuestos, Facturas y Pagos**, y mantiene una **sincronización automática de la tasa** mediante un API Centralizada propia. Todo esto protegiendo los decimales y cumpliendo la normativa del SENIAT sin alterar la moneda base de la compañía.

---

## 1. Cumplimiento de Estándares (Simplit Odoo 18)

Este módulo está construido bajo las siguientes directrices estrictas:

* **Idioma del Código:** El nombre del módulo, modelos, métodos y variables DEBEN estar estrictamente en Inglés.
* **Aplicación Principal:** Definido como `"application": True` en el Manifest.
* **Cero Hardcoding (Regla 1):** Las tasas, credenciales de API y URLs se configuran dinámicamente desde la UI o modelos dedicados.
* **Arquitectura Modular (Regla 2):** Un archivo físico `.py` y `.xml` por cada modelo heredado o creado.
* **Nomenclatura (Regla 3):** Todos los campos y modelos personalizados utilizan estrictamente el prefijo del módulo (`l10n_ve_ta_multicurrency_`).
* **Seguridad (Regla 4):** Todo modelo nuevo debe generar inmediatamente su regla de acceso en el archivo `security/ir.model.access.csv`.

---

## 2. Nomenclatura Estricta de Variables

Para evitar conflictos y cumplir con el estándar de geolocalización, todo campo nuevo inyectado en Odoo lleva el prefijo del módulo:

* ❌ **Incorrecto:** `f_currency_id`, `tasa_manual`, `api_token`.
* ✅ **Correcto:** `l10n_ve_ta_multicurrency_currency_id`, `l10n_ve_ta_multicurrency_guid`.

---

## 3. Estructura de Modelos y Campos Clave

### A. Sincronización de Tasa (API Centralizada & Cron)

Para proteger la infraestructura y gestionar licencias, Odoo no consumirá el BCV directamente, sino que se conectará a un API centralizada de Simplit.

* **Configuración del API (`l10n_ve_ta_multicurrency.api.config`):** Modelo dedicado a la configuración del servicio de tasas.
    * `l10n_ve_ta_multicurrency_enable_sync` (Boolean): Activa/Desactiva el job de sincronización automática.
    * `l10n_ve_ta_multicurrency_api_url` (Char): Endpoint del API Centralizada de Simplit.
    * `l10n_ve_ta_multicurrency_guid` (Char): Identificador único global del cliente. Se llenará posteriormente cuando el API del BCV esté lista para vincular la cuenta.
    * `company_id` (Many2one): Relación con la compañía actual.
* **Histórico de Sincronización (`l10n_ve_ta_multicurrency.rate.sync.log`):** Nuevo modelo para auditoría.
    * `name` (Char): Fecha y hora de ejecución.
    * `l10n_ve_ta_multicurrency_fetched_rate` (Float 12,6): Tasa obtenida del API.
    * `l10n_ve_ta_multicurrency_status` (Selection): Éxito / Error.
    * `l10n_ve_ta_multicurrency_response_msg` (Text): Respuesta cruda del servidor para depuración.
* **Tarea Programada (`ir.cron`):** Job periódico que valida si `enable_sync` es True. Al ejecutarse, arma el payload leyendo la URL y el `guid` de la configuración, y extrae dinámicamente el ID de la base de datos de PostgreSQL y la Licencia de Odoo directamente del entorno de ejecución (`ir.config_parameter`) para autenticarse contra el API de Simplit. **Una vez obtenida la tasa exitosamente, el cron es responsable de actualizar el modelo nativo de tasas de Odoo (`res.currency.rate`), creando o actualizando el registro del día para la moneda correspondiente, garantizando así que todos los cálculos nativos del sistema funcionen con la tasa oficial.**

### B. Moneda y Catálogo (`res.currency`, `product.template`)

* **`l10n_ve_ta_multicurrency_is_fiscal` (Boolean):** Marca la moneda como fiscal (Bs). Única a nivel global.
* **`l10n_ve_ta_multicurrency_list_price_fiscal` (Monetary):** Precio de venta en Bs. **Nota técnica:** Este campo debe ser estrictamente computado al vuelo (`compute='_compute_list_price_fiscal', store=False`) para no impactar el rendimiento ni ocupar espacio innecesario en la base de datos.

### C. Ventas y Facturación (Cabeceras: `sale.order`, `account.move`)

Gestión global del documento y almacenamiento de los totales en la moneda fiscal (VES).

* **Gestión de Tasa:**
    * `l10n_ve_ta_multicurrency_use_manual_rate` (Boolean): Activa la sobreescritura manual en presupuestos y facturas.
    * `l10n_ve_ta_multicurrency_rate` (Float 12,6): Tasa Bs/USD manual.
* **Totales Fiscales (Monetary - Almacenados en Bs):**
    * `l10n_ve_ta_multicurrency_taxable_amount` (Base Imponible / Gravable)
    * `l10n_ve_ta_multicurrency_exempt_amount` (Monto Exento)
    * `l10n_ve_ta_multicurrency_discount_amount` (Monto de Descuento)
    * `l10n_ve_ta_multicurrency_tax_amount` (Monto de Impuesto)
    * `l10n_ve_ta_multicurrency_total_amount` (Total General)

### D. Detalles de Líneas (`sale.order.line`, `account.move.line`)

Desglose a nivel de línea para precisión contable e impresión de reportes fiscales. Todos de tipo `Monetary` calculados en Bs.

* `l10n_ve_ta_multicurrency_price_unit` (Precio Unitario)
* `l10n_ve_ta_multicurrency_discount_amount` (Descuento de la línea)
* `l10n_ve_ta_multicurrency_exempt_amount` (Monto Exento de la línea)
* `l10n_ve_ta_multicurrency_taxable_amount` (Base Imponible de la línea)
* `l10n_ve_ta_multicurrency_tax_amount` (Impuesto de la línea)
* `l10n_ve_ta_multicurrency_total_amount` (Subtotal de la línea)
* **Apuntes Contables (Solo en `account.move.line`):**
    * `l10n_ve_ta_multicurrency_debit_amount` (Débito)
    * `l10n_ve_ta_multicurrency_credit_amount` (Crédito)

### E. Gestión de Pagos (`account.payment.register`, `account.payment`)

Para garantizar que la tasa de cambio en el momento del pago quede registrada y auditable. Se deben extender ambos modelos: el asistente (wizard) y el registro final.

* **Asistente de Pago (`account.payment.register`):**
    * `l10n_ve_ta_multicurrency_use_manual_rate` (Boolean): Activa la sobreescritura manual
    * `l10n_ve_ta_multicurrency_rate` (Float 12,6): Tasa aplicada al momento de registrar el pago (se trae por defecto la del día o la manual si aplica).
    * `l10n_ve_ta_multicurrency_amount` (Monetary): Monto visualizado en la moneda fiscal.
* **Registro de Pago (`account.payment`):**
    * `l10n_ve_ta_multicurrency_rate` (Float 12,6): Tasa histórica con la que se procesó el pago.
    * `l10n_ve_ta_multicurrency_amount` (Monetary): Monto total pagado en su equivalente fiscal (Bs).


   ### F. Agregar en los asientos contable de los pagos.
* **Apuntes Contables de los pagos:**
    * `l10n_ve_ta_multicurrency_debit_amount` (Débito)
    * `l10n_ve_ta_multicurrency_credit_amount` (Crédito)