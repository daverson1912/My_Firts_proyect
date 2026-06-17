# -*- coding: utf-8 -*-
from odoo import models, fields, api

class MyCustomModel(models.Model):
    _name = 'my_custom.model'
    _description = 'Modelo Personalizado de Ejemplo'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
    comentario = fields.Char(string='Comentario de Prueba')
