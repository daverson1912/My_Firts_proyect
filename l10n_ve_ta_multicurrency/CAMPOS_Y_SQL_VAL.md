# Guía de Campos Multimoneda y Validación en Base de Datos

Este documento detalla los campos referenciales de multimoneda agregados a los comprobantes de retención de IVA e ISLR en el módulo `l10n_ve_ta_multicurrency`, confirmando cuáles se guardan físicamente en la Base de Datos (BD) y proporcionando las consultas SQL (queries) para validarlo.

---

## 1. ¿Están guardados en la Base de Datos (BD)?

**SÍ, la gran mayoría.**
En Odoo, un campo calculado (`compute`) solo se almacena físicamente en las tablas de PostgreSQL si tiene el atributo `store=True` en su definición de Python. 

* **Campos con `store=True`**: Se calculan en el servidor y se guardan como columnas reales en las tablas de la base de datos.
* **Campos sin `store=True`** (o `store=False`): Se calculan dinámicamente "al vuelo" en memoria cuando el cliente web los solicita y **NO** ocupan espacio ni existen como columnas en la BD.

A continuación se detallan todos los campos según su modelo.

---

## 2. Detalle de Campos por Modelo

### A. Retención de IVA (`account.wh.iva`)
*Tabla en BD:* `account_wh_iva`

| Campo Técnico | Etiqueta (UI) | Tipo | Guardado en BD | Descripción / Fórmula |
| :--- | :--- | :--- | :---: | :--- |
| `l10n_ve_ta_multicurrency_amount_base` | Impuesto Base (IVA) (Ref.) | Monetary | **SÍ** | `amount_base * factor_tasa` (IVA Base en Bs) |
| `l10n_ve_ta_multicurrency_amount_total_ret` | Monto Total Retenido (Ref.) | Monetary | **SÍ** | `amount_total_ret * factor_tasa` (IVA Retenido en Bs) |
| `l10n_ve_ta_multicurrency_base` | Base Imponible Ref. | Monetary | **SÍ** | `amount_taxable_base * factor_tasa` |
| `l10n_ve_ta_multicurrency_total_invoice` | Monto Total Factura Ref. | Monetary | **SÍ** | `amount_total_invoice * factor_tasa` |
| `l10n_ve_ta_multicurrency_taxable_base` | Base Imponible Total Ref. | Monetary | **SÍ** | `amount_taxable_base * factor_tasa` |
| `l10n_ve_ta_multicurrency_exempt` | Monto Exento Ref. | Monetary | **SÍ** | `amount_exempt * factor_tasa` |
| `l10n_ve_ta_multicurrency_fiscal_id` | Moneda de Referencia | Many2one | NO | Moneda fiscal (Bs) usada para formatear los campos en la vista. |

---

### B. Retención de ISLR (`account.wh.islr`)
*Tabla en BD:* `account_wh_islr`

| Campo Técnico | Etiqueta (UI) | Tipo | Guardado en BD | Descripción / Fórmula |
| :--- | :--- | :--- | :---: | :--- |
| `l10n_ve_ta_multicurrency_amount_total_ret` | Total Retenido (Ref.) | Monetary | **SÍ** | `amount_total_ret * factor_tasa` (ISLR Retenido en Bs) |
| `l10n_ve_ta_multicurrency_amount_to_pay` | Monto a Pagar (Ref.) | Monetary | **SÍ** | `amount_to_pay * factor_tasa` |
| `l10n_ve_ta_multicurrency_total_invoice` | Monto del Documento (Ref.) | Monetary | **SÍ** | `amount_total_invoice * factor_tasa` |
| `l10n_ve_ta_multicurrency_taxable_base` | Base Imponible (Ref.) | Monetary | **SÍ** | `amount_taxable_base * factor_tasa` |
| `l10n_ve_ta_multicurrency_exempt` | Monto Exento (Ref.) | Monetary | **SÍ** | `amount_exempt * factor_tasa` |
| `l10n_ve_ta_multicurrency_fiscal_id` | Moneda de Referencia | Many2one | NO | Moneda fiscal (Bs). |

---

### C. Detalle de Líneas de ISLR (`account.wh.islr.line`)
*Tabla en BD:* `account_wh_islr_line`

| Campo Técnico | Etiqueta (UI) | Tipo | Guardado en BD | Descripción / Fórmula |
| :--- | :--- | :--- | :---: | :--- |
| `l10n_ve_ta_multicurrency_base_amount` | Base Imponible Ref. | Monetary | **SÍ** | `base_amount * factor_tasa` (Monto base en Bs) |
| `l10n_ve_ta_multicurrency_retention_amount` | Monto Retenido Ref. | Monetary | **SÍ** | `retention_amount * factor_tasa` (Retenido en Bs) |
| `l10n_ve_ta_multicurrency_subtrahend` | Sustraendo Ref. | Monetary | **SÍ** | `subtrahend * factor_tasa` (Sustraendo en Bs) |
| `l10n_ve_ta_multicurrency_subject_amount_display` | Base de la retención Ref. | Char | NO | Texto formateado: `"466.165,71 Bs (100%)"` |
| `l10n_ve_ta_multicurrency_retention_calculation_display` | Calc. Imp Ref. | Char | NO | Texto formateado: `"13.984,97 Bs (3%)"` |
| `l10n_ve_ta_multicurrency_fiscal_id` | Moneda de Referencia | Related | NO | Relacionado a la moneda de la retención padre. |

---

## 3. Consultas SQL (Queries) de Validación

Puedes ejecutar estas consultas en **pgAdmin**, **DBeaver** o desde la terminal de **psql** conectándote a la base de datos `odoo-18-multi`.

### A. Validar que las Columnas Existen en las Tablas (Estructura)
Estas consultas verifican si PostgreSQL realmente creó las columnas en sus respectivas tablas.

```sql
-- Verificar columnas creadas para Retención de IVA
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'account_wh_iva' 
  AND column_name LIKE 'l10n_ve_ta_multicurrency%';

-- Verificar columnas creadas para Retención de ISLR
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'account_wh_islr' 
  AND column_name LIKE 'l10n_ve_ta_multicurrency%';

-- Verificar columnas creadas para Líneas de ISLR
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'account_wh_islr_line' 
  AND column_name LIKE 'l10n_ve_ta_multicurrency%';
```

---

### B. Validar los Datos Almacenados (Valores Reales)
Estas consultas te permiten ver los montos nativos versus los montos en moneda de referencia (Bs) guardados en cada registro.

#### 1. Consulta para Retención de IVA:
```sql
SELECT 
    id, 
    name as numero_comprobante,
    amount_base as iva_base_original,
    l10n_ve_ta_multicurrency_amount_base as iva_base_referencia_bs,
    amount_total_ret as iva_ret_original,
    l10n_ve_ta_multicurrency_amount_total_ret as iva_ret_referencia_bs,
    l10n_ve_ta_multicurrency_total_invoice as total_factura_referencia_bs
FROM account_wh_iva
ORDER BY id DESC
LIMIT 5;
```

#### 2. Consulta para Retención de ISLR:
```sql
SELECT 
    id, 
    name as numero_comprobante,
    amount_taxable_base as base_imponible_original,
    l10n_ve_ta_multicurrency_taxable_base as base_imponible_referencia_bs,
    amount_total_ret as islr_ret_original,
    l10n_ve_ta_multicurrency_amount_total_ret as islr_ret_referencia_bs,
    amount_to_pay as neto_pagar_original,
    l10n_ve_ta_multicurrency_amount_to_pay as neto_pagar_referencia_bs
FROM account_wh_islr
ORDER BY id DESC
LIMIT 5;
```

#### 3. Consulta para Detalles/Líneas de ISLR:
```sql
SELECT 
    id,
    base_amount as base_original,
    l10n_ve_ta_multicurrency_base_amount as base_referencia_bs,
    retention_amount as retencion_original,
    l10n_ve_ta_multicurrency_retention_amount as retencion_referencia_bs,
    subtrahend as sustraendo_original,
    l10n_ve_ta_multicurrency_subtrahend as sustraendo_referencia_bs
FROM account_wh_islr_line
ORDER BY id DESC
LIMIT 5;
```
