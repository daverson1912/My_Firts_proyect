# Venezuela - Gestión Fiscal Híbrida (Simplit)

## Descripción

Módulo de Odoo 18 para la automatización de retenciones de IVA para Contribuyentes Especiales en Venezuela.

## Estado del Desarrollo

### ✅ Fase 1: Modelo de Empresa (COMPLETADA)

**Archivos creados:**
- `__manifest__.py` - Configuración del módulo
- `__init__.py` - Importación de módulos
- `models/res_company.py` - Extensión del modelo de empresa
- `views/res_company_views.xml` - Vista de configuración
- `security/ir.model.access.csv` - Reglas de acceso

**Funcionalidad implementada:**
- Campo `l10n_ve_is_withholding_agent` en `res.company`
- Visibilidad automática solo para empresas venezolanas
- Sección "Venezuela - Configuración Fiscal" en vista de empresa

### ✅ Fase 2: Automatización de Retenciones (COMPLETADA)

**Archivos creados/modificados:**
- `models/simplitfiscal_config.py` - Modelo de configuración centralizada
- `models/account_move_line.py` - Hooks para reemplazo automático de impuestos
- `models/account_move.py` - Campo relacionado de retención
- `models/account_tax.py` - Flag `is_simplit_tax`
- `models/res_partner.py` - Campo de tipo de retención por proveedor
- `views/simplitfiscal_config_views.xml` - Interfaz de configuración con pestañas
- `views/res_partner_views.xml` - Vista de proveedor extendida

**Funcionalidad implementada:**
- ✅ Generación automática de impuestos base (IVA 16%, 8%, retenciones)
- ✅ Generación automática de grupos combo (SP IVA +RET 75%, SP IVA +RET 100%)
- ✅ Configuración por proveedor de tipo de retención (75% o 100%)
- ✅ Reemplazo automático de impuestos en facturas de compra
- ✅ Funciona en todos los escenarios:
  - ✅ Creación manual de facturas
  - ✅ Creación desde órdenes de compra
  - ✅ Importación programática de facturas
- ✅ Logging detallado para diagnóstico
- ✅ Validaciones robustas

**Cumplimiento de reglas:**
- ✅ Odoo 18 syntax (sin `attrs`, usa `invisible` directo)
- ✅ PEP8 compliance
- ✅ Docstrings en métodos
- ✅ Licencia OPL-1

## Instalación

1. El módulo está ubicado en `odoo-enterprise/l10n_ve_simplit_fiscal`
2. Reiniciar el servidor Odoo
3. Actualizar lista de módulos
4. Buscar "Venezuela - Gestión Fiscal Híbrida"
5. Instalar

## Configuración Inicial

### Paso 1: Configurar la Empresa
1. Ir a **Configuración** → **Empresas** → Seleccionar empresa
2. En pestaña **General**, configurar:
   - **País:** Venezuela 🇻🇪 (REQUERIDO)
   - Guardar

### Paso 2: Configurar Simplit Fiscal
1. Buscar **"Configuración Simplit Fiscal"** en el menú
2. Crear nueva configuración:
   - **Nombre:** "Configuración Fiscal Venezuela"
   - **Compañía:** Seleccionar tu empresa
   - En pestaña **"Configuración"**:
     - ✅ Marcar **"Es Agente de Retención IVA"**
     - Seleccionar **"Tipo de Retención por Defecto"**: 75% o 100%
   - Guardar
3. Ir a pestaña **"Impuestos"**
4. Hacer clic en **"Generar Impuestos"**
5. Esperar confirmación: "✓ Impuestos generados exitosamente"

### Paso 3: Configurar Proveedores
1. Ir a **Contactos** → **Proveedores**
2. Para cada proveedor sujeto a retención:
   - Abrir el proveedor
   - Ir a pestaña **"Ventas y Compras"**
   - En sección **"Venezuela - Configuración Fiscal"**:
     - Seleccionar **"Porcentaje de retención de IVA"**: 75% o 100%
   - Guardar

## Uso

### Crear Factura de Compra con Retención

1. Ir a **Contabilidad** → **Proveedores** → **Facturas**
2. Crear nueva factura
3. Seleccionar proveedor (que tenga retención configurada)
4. Agregar líneas de productos con IVA
5. **✨ AUTOMÁTICAMENTE:** El sistema reemplazará:
   - "IVA 16%" → "SP IVA +RET 75%" (o 100%)
   - "IVA 8%" → "SP IVAR +RET 75%" (o 100%)
6. Verificar cálculos:
   - Ejemplo con IVA 16% y retención 75%:
     - Subtotal: 100.00
     - IVA SP 16%: +16.00
     - Retención IVA 75%: -12.00
     - **Total: 104.00** ✅

## Troubleshooting

### El reemplazo automático NO funciona

**Causa 1: Empresa no es venezolana**
- **Solución:** Configuración → Empresas → Cambiar país a Venezuela

**Causa 2: No generaste los impuestos**
- **Solución:** Configuración Simplit Fiscal → Pestaña "Impuestos" → "Generar Impuestos"

**Causa 3: Empresa no es Agente de Retención**
- **Solución:** Configuración Simplit Fiscal → Marcar "Es Agente de Retención IVA"

**Causa 4: Proveedor sin retención configurada**
- **Solución:** Editar proveedor → Pestaña "Ventas y Compras" → Configurar porcentaje de retención

### Ver mensajes de diagnóstico

Iniciar servidor con logs en consola:
```bash
python odoo-bin -c odoo.conf --dev=all --logfile=-
```

Buscar mensajes `[FISCAL]` que indican qué está pasando.

## Próximas Fases

- [ ] Fase 3: Generación de Comprobantes de Retención
- [ ] Fase 4: Reportes Fiscales
- [ ] Fase 5: Integración con SENIAT
