import re
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    """ Extensión de contactos para vincularlos con clientes de WispHub """
    """ Contact extension to link them with WispHub customers """
    _inherit = 'res.partner'

    # Identificador único de cliente / Unique customer identifier
    whub_customer_id = fields.Char(string='IDs Cliente WispHub', help="ID(s) único(s) del cliente en WispHub. Puede contener varios separados por coma.", copy=False)

    def _normalize_vat(self, vat):
        """ Normaliza el RIF o Cédula a formato estándar venezolano si corresponde """
        if not vat:
            return False
        # Limpiar espacios en blanco y convertir a mayúsculas
        v = vat.strip().upper()
        # Eliminar puntos, guiones y espacios intermedios para facilitar comparación
        v = re.sub(r'[\.\s\-_]', '', v)
        
        if not v:
            return False
            
        # Intentar coincidencia con formatos venezolanos (V, E, J, G, P, C)
        match = re.match(r'^([VEJGPC])(\d+)$', v)
        if match:
            prefix = match.group(1)
            digits = match.group(2)
            # RIF venezolano (tanto natural como jurídico) tiene siempre 9 dígitos tras el prefijo (8 + 1 verificador)
            if len(digits) == 9:
                return f"{prefix}-{digits[:8]}-{digits[8]}"
            else:
                return f"{prefix}-{digits}"
        return v


    def _normalize_whub_customer_id(self, whub_id):
        """ Normaliza el ID o IDs de cliente WispHub eliminando espacios alrededor de las comas """
        if not whub_id:
            return False
        return ','.join([x.strip() for x in whub_id.split(',') if x.strip()])

    @api.constrains('whub_customer_id')
    def _check_whub_customer_id_unique(self):
        """ Valida que cada ID de WispHub en la lista de comas sea único en la base de datos """
        for rec in self:
            if not rec.whub_customer_id:
                continue
            # Obtener IDs individuales
            ids = [x.strip() for x in rec.whub_customer_id.split(',') if x.strip()]
            for w_id in ids:
                domain = [
                    ('id', '!=', rec.id),
                    '|', ('whub_customer_id', '=', w_id),
                    '|', ('whub_customer_id', '=ilike', f'{w_id},%'),
                    '|', ('whub_customer_id', '=ilike', f'%,{w_id}'),
                         ('whub_customer_id', '=ilike', f'%,{w_id},%')
                ]
                duplicate = self.search(domain, limit=1)
                if duplicate:
                    raise ValidationError(_(
                        "El ID de cliente WispHub '%s' ya está asignado al contacto '%s'."
                    ) % (w_id, duplicate.name))

    @api.constrains('vat')
    def _check_vat_uniqueness_and_integrity(self):
        """ Valida la integridad de formato del RIF/Cédula y su unicidad por compañía """
        for rec in self:
            if not rec.vat:
                continue
            
            # Normalizar
            normalized = rec._normalize_vat(rec.vat)
            
            # Validación de formato si empieza con un prefijo fiscal venezolano
            first_char = rec.vat.strip().upper()[0] if rec.vat.strip() else ''
            if first_char in ['V', 'E', 'J', 'G', 'P', 'C']:
                clean_vat = re.sub(r'[\.\s\-_]', '', rec.vat.strip().upper())
                if not re.match(r'^([VEJGPC])\d{5,10}$', clean_vat):
                    raise ValidationError(_(
                        "El formato del RIF o Cédula '%s' no es válido. Debe usar un formato correcto "
                        "(ej. V-12345678 o J-12345678-9)."
                    ) % rec.vat)
            
            # Validación de unicidad
            duplicate_domain = [('id', '!=', rec.id)]
            if rec.company_id:
                duplicate_domain.append(('company_id', 'in', [rec.company_id.id, False]))
            else:
                duplicate_domain.append(('company_id', '=', False))
                
            duplicate_domain.append('|')
            duplicate_domain.append(('vat', '=', rec.vat))
            duplicate_domain.append('|')
            duplicate_domain.append(('vat', '=', normalized))
            duplicate_domain.append('|')
            duplicate_domain.append(('vat', '=', rec.vat.replace('-', '')))
            duplicate_domain.append(('vat', '=', normalized.replace('-', '')))
            
            duplicate = self.search(duplicate_domain, limit=1)
            if duplicate:
                raise ValidationError(_(
                    "El RIF o Cédula '%s' ya está registrado en el contacto '%s'."
                ) % (rec.vat, duplicate.name))

    def _determine_is_company_from_vat(self, vat):
        """ Determina si el contacto es una compañía en base al prefijo del RIF """
        if not vat:
            return None
        v = vat.strip().upper()
        if v.startswith(('J', 'G', 'C')):
            return True
        elif v.startswith(('V', 'E', 'P')):
            return False
        return None

    @api.onchange('vat')
    def _onchange_vat_determine_company_type(self):
        """ Determina dinámicamente si es persona natural o jurídica en la UI de Odoo """
        if self.vat:
            normalized = self._normalize_vat(self.vat)
            if normalized:
                self.vat = normalized
            is_company = self._determine_is_company_from_vat(self.vat)
            if is_company is not None:
                self.is_company = is_company

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'vat' in vals and vals['vat']:
                vals['vat'] = self._normalize_vat(vals['vat'])
                # Autodetectar tipo de persona (individual o jurídica)
                is_company = self._determine_is_company_from_vat(vals['vat'])
                if is_company is not None and 'is_company' not in vals:
                    vals['is_company'] = is_company
            if 'whub_customer_id' in vals and vals['whub_customer_id']:
                vals['whub_customer_id'] = self._normalize_whub_customer_id(vals['whub_customer_id'])
        return super().create(vals_list)

    def write(self, vals):
        if 'vat' in vals and vals['vat']:
            vals['vat'] = self._normalize_vat(vals['vat'])
            # Autodetectar tipo de persona (individual o jurídica)
            is_company = self._determine_is_company_from_vat(vals['vat'])
            if is_company is not None and 'is_company' not in vals:
                vals['is_company'] = is_company
        if 'whub_customer_id' in vals and vals['whub_customer_id']:
            vals['whub_customer_id'] = self._normalize_whub_customer_id(vals['whub_customer_id'])
        return super().write(vals)


