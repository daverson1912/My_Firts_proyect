# Guía de Pruebas: Integración Fiscal y Multimoneda VE (Odoo 18)

Esta guía detalla los pasos para validar que la integración entre el sistema multimoneda y el módulo fiscal de retenciones está funcionando correctamente bajo cualquier configuración de moneda base.

---

## 1. Validación de Configuración de Tasas

### Escenario A: Compañía con Base USD (Dólares)
1. Ve a **Ajustes > Multimoneda VE**.
2. Selecciona la opción: **"Moneda de la Compañía es Referencial (Multiplicar)"**.
3. Haz clic en **Sincronizar Ahora**.
4. **Resultado Esperado**: La "Tasa Actual" debe mostrar el valor del BCV (ej: 489,55) y en la lista de monedas, el VES debe tener esa misma tasa.

### Escenario B: Compañía con Base VES (Bolívares)
1. Ve a **Ajustes > Multimoneda VE**.
2. Selecciona la opción: **"Moneda de la Compañía es Local/Fiscal (Dividir)"**.
3. Haz clic en **Sincronizar Ahora**.
4. **Resultado Esperado**: En el cuadro de resumen verás **489,55 Bs/USD** (amigable), pero en la lista de monedas el USD tendrá una tasa técnica (ej: 0,00204). Odoo usará esto para dividir y llegar al monto correcto.

---

## 2. Flujo de Facturación y Retenciones (Fiscal)

### Prueba de Retención de IVA
1. Crea una **Factura de Proveedor** en **Dólares (USD)**.
2. Agrega una línea de producto con **IVA 16%**.
3. Haz clic en el botón **"Retención de IVA"** (proporcionado por el módulo fiscal).
4. **Validación**:
   - El sistema debe generar un documento de retención.
   - Entra al documento de retención y verifica la pestaña de **Bolívares (VES)**.
   - El monto retenido debe ser exactamente: `(Monto USD * Tasa BCV) * % Retención`.
   - Verifica que el monto en Bolívares coincida con la tasa del día de la factura.

### Prueba de Retención de ISLR
1. En la misma factura o una nueva, aplica una **Retención de ISLR**.
2. Verifica que el comprobante de ISLR generado muestre la base imponible y el monto retenido en **Bolívares**, cumpliendo con la normativa.

---

## 3. Resumen en Factura (Footer)

1. Abre cualquier factura (Cliente o Proveedor).
2. Ve al final de la factura (pestaña Otra Información o el resumen de totales).
3. **Resultado Esperado**: Debes visualizar un cuadro resumen que indique:
   - **Total Neto (VES)**
   - **Total IVA (VES)**
   - **Total Retenido (VES)**
   - **Total a Pagar (VES)**
   - Este cuadro debe calcularse dinámicamente usando la tasa de la factura.

---

## 4. Reportes Legales (Libros de IVA)

1. Ve a **Contabilidad > Informes > Venezuela > Libro de Compras/Ventas**.
2. Genera el reporte para el mes actual.
3. **Validación**:
   - Todas las columnas (Base Imponible, IVA, Retenciones) deben mostrarse en **Bolívares (VES)**.
   - Si la factura original fue en USD, el reporte debe haber usado la tasa de ese día para la conversión.
   - Los números deben cuadrar con los comprobantes de retención generados en el paso anterior.

---

## 5. Mensajes de Error (Prueba de Fallos)

1. Desconecta el middleware o cambia la URL a una inexistente en `globalConfig.json`.
2. Intenta sincronizar.
3. **Resultado Esperado**: El sistema debe mostrar un mensaje amigable: 
   *"Ocurrió un inconveniente al conectar con el servicio de tasas. Por favor, verifique su conexión a internet o intente más tarde."*
   (Sin códigos de error técnicos ni trazas de Python).

---

## 6. Checklist Final de Cálculos
- [ ] ¿La tasa en el resumen de Ajustes es fácil de leer (Bolívares por Dólar)?
- [ ] ¿Las retenciones en facturas USD generan montos en VES correctos?
- [ ] ¿Los reportes (PDF/Excel) están 100% en Bolívares?
- [ ] ¿El sistema se comporta bien si cambio la moneda base de la compañía?
