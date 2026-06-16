/** @odoo-module **/
import { TaxTotalsComponent } from "@account/components/tax_totals/tax_totals";
import { patch } from "@web/core/utils/patch";

patch(TaxTotalsComponent.prototype, {
    /**
     * EN: Override formatData to suppress native Odoo multicurrency conversion in the totals widget.
     * ES: Invalida formatData para suprimir la conversión multimoneda nativa de Odoo en el widget de totales.
     */
    formatData(props) {
        super.formatData(props);
        if (this.totals) {
            // Force display_in_company_currency to false to hide secondary currency in tax groups
            this.totals.display_in_company_currency = false;
            
            // To ensure the Total line doesn't show conversion, we can spoof the company currency 
            // as being the same as the document currency within the widget's local data.
            this.totals.company_currency_id = this.totals.currency_id;
            this.totals.company_currency_pd = this.totals.currency_pd;
        }
    },

    /**
     * EN: Intercept monetary formatting to strip any parenthesized conversions.
     * ES: Intercepta el formato monetario para eliminar cualquier conversión entre paréntesis.
     */
    formatMonetary(value) {
        let res = super.formatMonetary(value);
        if (typeof res === 'string' && res.includes('(')) {
            // Cut off everything from the first parenthesis (the conversion)
            return res.split('(')[0].trim();
        }
        return res;
    }
});
