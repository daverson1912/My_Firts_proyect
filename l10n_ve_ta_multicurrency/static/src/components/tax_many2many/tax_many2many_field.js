/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/views/fields/many2many_tags/many2many_tags_field";
import { Domain } from "@web/core/domain";
import { getFieldDomain } from "@web/model/relational_model/utils";

/**
 * Widget tax_many2many: igual que many2many_tags pero oculta los grupos
 * de impuestos (amount_type = 'group') del dropdown por defecto.
 * El botón nativo "Buscar más..." sigue disponible para acceder a todo.
 */
export class TaxMany2ManyField extends Many2ManyTagsField {
    static template = "l10n_ve_ta_multicurrency.TaxMany2ManyField";

    getDomain() {
        const base = Domain.and([
            getFieldDomain(this.props.record, this.props.name, this.props.domain),
        ]);
        return Domain.and([base, [["amount_type", "!=", "group"]]]).toList(
            this.props.context
        );
    }
}

export const taxMany2ManyField = {
    ...many2ManyTagsField,
    component: TaxMany2ManyField,
};

registry.category("fields").add("tax_many2many", taxMany2ManyField);
