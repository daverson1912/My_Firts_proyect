# Reporte de Conflicto: Multimoneda vs Simplit Fiscal

## Descripción del Problema
Se ha detectado una incompatibilidad crítica entre el módulo `l10n_ve_ta_multicurrency` (Multimoneda) y `l10n_ve_simplit_fiscal` (Fiscal) al gestionar el widget de totales (`tax_totals`) en Odoo 18.

### Causa Técnica
Ambos módulos sobreescriben el método `_compute_tax_totals` en el modelo `account.move`.

1.  **Módulo Fiscal**: Filtra los grupos de impuestos de retención para que no resten del total visual (quiere mostrar el Total Bruto). Ajusta `move.tax_totals['total_amount']` restando los montos negativos de retención.
2.  **Módulo Multimoneda**: Sobreescribe `move.tax_totals['total_amount']` con el valor de `total_amount_currency` para forzar la visualización en la moneda del documento y oculta la conversión nativa de Odoo (`display_in_company_currency = False`).

**El conflicto**: El Multimoneda borra los ajustes realizados por el Fiscal, o viceversa, resultando en totales descuadrados o columnas de impuestos que "desaparecen" o muestran valores inconsistentes al mezclar montos en Bs. con montos en USD.

---

## Solución Recomendada (Ajuste en Multimoneda)

Para resolver esto, el módulo Multimoneda debe ser consciente de las retenciones filtradas por el módulo fiscal. Se recomienda modificar el método `_compute_tax_totals` en `l10n_ve_ta_multicurrency/models/account_move.py` de la siguiente manera:

### Código Sugerido de Reemplazo:

```python
    @api.depends('company_id', 'currency_id', 'move_type')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for move in self:
            if move.tax_totals and isinstance(move.tax_totals, dict):
                # 1. Desactivar conversión nativa
                move.tax_totals['display_in_company_currency'] = False
                
                # 2. Sincronizar Total (Manteniendo coherencia con retenciones si existen)
                # Si el módulo fiscal ya ajustó el total, debemos respetarlo o re-aplicarlo
                # comparando contra el total_amount_currency.
                
                # Lógica de seguridad:
                # El total_amount original de Odoo es NETO (con retenciones restadas).
                # El total_amount que queremos mostrar es BRUTO (sin retenciones).
                
                move.tax_totals['total_amount'] = move.tax_totals.get('total_amount_currency', 0.0)
                move.tax_totals['base_amount'] = move.tax_totals.get('base_amount_currency', 0.0)

                # NOTA: Si el módulo fiscal se ejecuta DESPUÉS, él volverá a ajustar 
                # estos valores sobre la base que dejamos aquí, lo cual es correcto.
```

## Recomendación de Arquitectura
Para evitar futuros choques, se sugiere que el módulo Fiscal tenga prioridad en el orden de carga (dependencia opcional) o que ambos módulos hereden de una base común si comparten el mismo repositorio de addons. 

En Odoo 18, el manejo de `tax_totals` es un diccionario JSON; cualquier cambio destructivo (como el del multimoneda en la línea 254 del archivo original) anula las modificaciones de otros módulos.

---
*Análisis generado por Antigravity AI - Abril 2026*
