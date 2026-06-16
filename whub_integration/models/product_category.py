from odoo import fields, models

class ProductCategory(models.Model):
    _inherit = 'product.category'

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    whub_category_name = fields.Char(string='WispHub Category Name')

    _sql_constraints = [
        ('whub_category_name_uniq', 'unique(whub_category_name, company_id)', 'The WispHub category name must be unique per company!')
    ]
