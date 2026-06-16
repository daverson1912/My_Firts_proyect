# -*- coding: utf-8 -*-
{
    'name': 'Mi Módulo Personalizado',
    'version': '18.0.1.0.0',
    'summary': 'Módulo base personalizado para mi entorno de Odoo',
    'description': """
        Módulo personalizado creado para pruebas y desarrollo en Odoo v18.
    """,
    'author': 'daverson1912',
    'website': 'https://github.com/daverson1912/My_Firts_proyect',
    'category': 'Uncategorized',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
