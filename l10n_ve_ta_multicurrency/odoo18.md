name: odoo-18-simplit-standards
description: Fuerzas las mejores prácticas de Odoo 18 para la creación de módulos, convenciones de nomenclatura, seguridad, cero-hardcoding, manejo multimoneda, rendimiento del ORM y documentación bilingüe.

---

# Estándares de Desarrollo Odoo 18 (Simplit)

Este skill define las reglas **OBLIGATORIAS** para todo el desarrollo en Odoo. El objetivo es garantizar la compatibilidad, evitar conflictos con otros módulos y mantener un código limpio, rápido, escalable y perfectamente documentado.

---

## 1. Regla de Oro: CERO Hardcoding

Está **ESTRICTAMENTE PROHIBIDO** "cablear" (hardcode) valores, nombres, tasas de impuestos, cuentas contables o IDs en el código Python o XML.

- Todo valor dinámico debe ser configurable por el usuario.
- Utiliza `res.config.settings` (Ajustes de la Compañía) para configuraciones globales.
- Utiliza **Maestros de Datos** (ej. `account.tax`, `res.partner`) para reglas de negocio.

---

## 2. Arquitectura del Módulo y Archivos

Todo módulo nuevo debe estar estructurado de forma modular y ordenada.

- **Tipo de Módulo:** Todo módulo principal debe definirse como una aplicación en el `__manifest__.py` usando `"application": True`.
- **Orden del Manifest:** En la lista `data`, el archivo `security/ir.model.access.csv` SIEMPRE debe ir de primero.
- **Un Archivo por Modelo:** Si se hereda o se crea un modelo, debe existir en su propio archivo físico que coincida con el nombre del modelo.
  - **Ejemplo Correcto:** Si modificas `account.move`, crea `models/account_move.py`.
  - **Ejemplo Incorrecto:** Mezclar herencias de facturas y contactos en un archivo genérico `models.py`.

---

## 3. Convenciones de Nomenclatura (Localización)

Al agregar campos a modelos estándar de Odoo (`res.partner`, `account.move`, etc.), **DEBES** usar el prefijo de localización o del proyecto (`l10n_ve_` o `simplit_`).

### ❌ Incorrecto (Nombres genéricos causan conflictos)

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_wh_iva_agent = fields.Boolean() # MAL: Nombre genérico
```

### ✅ Correcto (Con prefijos)

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_ve_is_wh_iva_agent = fields.Boolean()
```

- **Nuevos Modelos:** Usa la notación de puntos con el prefijo (ej. `l10n_ve.wh.iva`).
- **IDs en XML:** Usa el patrón `view_{model_name}_{view_type}_{suffix}` (ej. `view_partner_form_inherit_l10n_ve_fiscal`).

---

## 4. Seguridad y Permisos (Obligatorio)

Odoo bloqueará cualquier modelo nuevo si no tiene permisos definidos.

- **Cada vez** que crees un modelo nuevo, DEBES generar inmediatamente su regla de acceso en el archivo `security/ir.model.access.csv`.
- Define los grupos correctamente (ej. `base.group_user` para lectura, `account.group_account_manager` para escritura/borrado).

---

## 5. Documentación de Código Bilingüe (Docstrings)

- **Obligatorio:** Cada método o función nueva debe incluir un _docstring_ explicativo.
- **Bilingüe:** La documentación interna del código debe estar escrita obligatoriamente en **Inglés y Español**.
- **Estructura:** Debe explicar brevemente qué hace la función, sus parámetros (Args/Params) y lo que retorna (Return).

### ✅ Ejemplo de Documentación Correcta:

```python
def calculate_retention(self, base_amount):
    """
    EN: Calculates the retention amount based on the partner's fiscal configuration.
    ES: Calcula el monto de retención basado en la configuración fiscal del contacto.

    :param base_amount: Float. Base amount for the tax calculation / Monto base para el cálculo.
    :return: Float. Calculated retention amount / Monto de retención calculado.
    """
    pass
```

---

## 6. Textos y Traducciones (I18n)

- **NUNCA** devuelvas mensajes de error o strings para el usuario en crudo.
- Todo texto debe estar envuelto en la función `_()` para permitir traducciones en la interfaz.
  - _Incorrecto:_ `raise ValidationError("El proveedor no tiene retención")`
  - _Correcto:_ `raise ValidationError(_("El proveedor no tiene retención"))` (Requiere importar `from odoo import _`).

---

## 7. Rendimiento del ORM (Anti N+1)

- **NUNCA** uses métodos como `.search()`, `.create()` o `.write()` dentro de un bucle `for record in self:`.
- Agrupa los datos y realiza operaciones masivas (batch) fuera del bucle usando `mapped()`, `filtered()` o construyendo diccionarios.

---

## 8. Campos Calculados (Compute)

- Un método de tipo `@api.depends` (campo calculado) **TIENE QUE ASIGNAR UN VALOR** al campo para cada registro en el bucle, sin excepción. Si usas un `if`, debes tener un `else` que asigne `False`, `0` o el valor por defecto.

---

## 9. Estándares para Vistas XML (Odoo 18)

- **Prohibido el uso de `attrs`:** En Odoo 18, `attrs` está obsoleto. Usa los atributos directamente evaluando el dominio (`invisible="state == 'draft'"`).
- **XPath Quirúrgico:** Al heredar una vista, nunca reemplaces bloques enteros de código. Usa `xpath` específicamente en el campo o elemento que necesitas modificar (ej. `<xpath expr="//field[@name='partner_id']" position="after">`).

---

## 10. Reglas para Multimoneda (Campos Monetarios)

Dado que la base de datos operará en una moneda (ej. USD) pero los reportes fiscales en otra (ej. VES):

- TODO campo de dinero debe ser de tipo `fields.Monetary`.
- TODO campo `Monetary` DEBE tener su respectivo campo `currency_field` definido (o heredar el `currency_id` de la compañía o del documento).
- NUNCA uses `fields.Float` para manejar dinero.

---

## 11. Checklist de Aprobación del Agente

Antes de entregar el código, el agente debe verificar internamente:

- [ ] ¿Es configurable (cero hardcoding)?
- [ ] ¿Los campos nuevos tienen el prefijo correcto?
- [ ] ¿Cada función/método tiene su docstring bilingüe (EN/ES)?
- [ ] ¿Los textos de usuario y errores usan la función de traducción `_()`?
- [ ] ¿Se crearon los permisos en `ir.model.access.csv`?
- [ ] ¿Las operaciones de Base de Datos están fuera de bucles `for`?
- [ ] ¿Los campos calculados asignan valor a todos los registros?
- [ ] ¿Los campos de dinero usan `fields.Monetary` vinculados a su moneda?

```

```
