# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestWHubValidation(TransactionCase):

    def setUp(self):
        super(TestWHubValidation, self).setUp()
        self.Partner = self.env['res.partner']
        self.Template = self.env['product.template']
        self.Category = self.env['product.category']
        self.Product = self.env['product.product']

        # Crear una compañía de prueba
        self.test_company = self.env['res.company'].create({
            'name': 'Test Company Validation',
        })

    def test_01_vat_normalization(self):
        """ Verificar que la normalización de RIF/Cédula funcione correctamente """
        partner = self.Partner.new()
        
        # Casos válidos con prefijo de persona natural
        self.assertEqual(partner._normalize_vat('v12345678'), 'V-12345678')
        self.assertEqual(partner._normalize_vat('V-12345678'), 'V-12345678')
        self.assertEqual(partner._normalize_vat(' v-12.345.678 '), 'V-12345678')
        
        # Casos válidos con prefijo jurídico
        self.assertEqual(partner._normalize_vat('j123456789'), 'J-12345678-9')
        self.assertEqual(partner._normalize_vat('J-12345678-9'), 'J-12345678-9')
        self.assertEqual(partner._normalize_vat(' J.12345678-9 '), 'J-12345678-9')
        
        # Casos válidos sin dígito verificador al final para jurídico
        self.assertEqual(partner._normalize_vat('j12345678'), 'J-12345678')
        
        # Otros prefijos
        self.assertEqual(partner._normalize_vat('g200000001'), 'G-20000000-1')
        self.assertEqual(partner._normalize_vat('e80000000'), 'E-80000000')

    def test_02_vat_format_validation(self):
        """ Verificar que el formato del RIF/Cédula sea validado """
        # RIF Inválido (muy corto)
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Partner RIF Corto',
                'vat': 'V-123',
            })

        # RIF Inválido (muy largo)
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Partner RIF Largo',
                'vat': 'V-1234567890123',
            })

        # RIF Inválido (caracteres no permitidos tras el prefijo)
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Partner RIF Caracteres',
                'vat': 'V-123A5678',
            })

    def test_03_vat_uniqueness(self):
        """ Verificar que se impida duplicados del RIF dentro de la misma compañía """
        # Crear primer contacto
        partner1 = self.Partner.create({
            'name': 'Contacto RIF 1',
            'vat': 'V-12345678',
            'company_id': self.test_company.id,
        })
        
        # Intentar crear un segundo contacto con el mismo RIF normalizado
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Contacto RIF Duplicado Mayuscula',
                'vat': 'v-12345678',
                'company_id': self.test_company.id,
            })
            
        # Intentar crear un segundo contacto con el mismo RIF sin guiones
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Contacto RIF Duplicado Sin Guion',
                'vat': 'V12345678',
                'company_id': self.test_company.id,
            })

    def test_04_whub_customer_id_uniqueness(self):
        """ Verificar que se impida duplicados de IDs de cliente WispHub """
        # Crear primer contacto con un ID
        self.Partner.create({
            'name': 'Cliente WH 1',
            'whub_customer_id': '101, 102',
        })
        
        # Intentar crear otro contacto con un ID colisionante en lista
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Cliente WH Duplicado',
                'whub_customer_id': '102',
            })

        # Intentar crear otro contacto con ID colisionante en lista separada por comas
        with self.assertRaises(ValidationError):
            self.Partner.create({
                'name': 'Cliente WH Duplicado Comas',
                'whub_customer_id': '205, 101, 206',
            })

    def test_05_whub_product_id_uniqueness(self):
        """ Verificar que se impida duplicados de IDs de producto/plan WispHub """
        # Crear primer producto con ID único
        self.Template.create({
            'name': 'Plan Fibra 100M',
            'whub_product_id': 'plan_100, plan_100_promo',
        })
        
        # Intentar crear otro producto con ID colisionante
        with self.assertRaises(ValidationError):
            self.Template.create({
                'name': 'Plan Fibra 100M Clon',
                'whub_product_id': 'plan_100',
            })

    def test_06_wizard_homologation_vat_fallback(self):
        """ Verificar que el asistente de homologación use el RIF/Cédula como fallback para evitar duplicación """
        # Crear contacto existente en Odoo con un RIF normalizado
        existing_partner = self.Partner.create({
            'name': 'Cliente Existente Real',
            'vat': 'V-12345678',
            'company_id': self.test_company.id,
        })
        
        # Instanciar el Wizard Principal
        main_wizard = self.env['whub.homologation.wizard'].create({
            'company_id': self.test_company.id,
        })
        
        # Crear la línea de homologación de cliente (que simula provenir de WispHub)
        customer_line = self.env['whub.homologation.customer.line'].create({
            'wizard_id': main_wizard.id,
            'whub_customer_name': 'Cliente Existente WispHub',
            'whub_customer_id': 'w_cust_999',
            'whub_fiscal_id': 'v12345678', # RIF sin normalizar pero coincidente
        })
        
        # Instanciar el Wizard de Selección de Creación
        selection_wizard = self.env['whub.creation.selection.wizard'].create({
            'parent_wizard_id': main_wizard.id,
        })
        
        # Crear la línea de selección de creación referenciando a la línea de cliente
        self.env['whub.creation.selection.line'].create({
            'wizard_id': selection_wizard.id,
            'source_line_id': f'cust_{customer_line.id}',
            'res_type': 'customer',
            'is_selected': True,
        })
        
        # Ejecutar la confirmación de la creación masiva
        selection_wizard.action_confirm_creation()
        
        # Verificar que NO se haya creado un nuevo partner, sino que se vinculó al existente
        self.assertEqual(customer_line.odoo_partner_id.id, existing_partner.id)
        
        # Verificar que se haya anexado el ID de cliente de WispHub al partner existente
        self.assertEqual(existing_partner.whub_customer_id, 'w_cust_999')

    def test_07_partner_type_autodetection(self):
        """ Verificar que is_company se detecte correctamente según el prefijo del RIF """
        # Caso A: Persona Jurídica (RIF empieza por J) -> is_company = True
        company_partner = self.Partner.create({
            'name': 'Corporación Comercial J-1',
            'vat': 'J-12345678-9',
        })
        self.assertTrue(company_partner.is_company)
        self.assertEqual(company_partner.company_type, 'company')

        # Caso B: Persona Natural (RIF empieza por V) -> is_company = False
        individual_partner = self.Partner.create({
            'name': 'Juan Pérez',
            'vat': 'V-12345678-9',
        })
        self.assertFalse(individual_partner.is_company)
        self.assertEqual(individual_partner.company_type, 'person')

        # Caso C: Cédula Persona Natural (Cédula empieza por V sin dígito verificador) -> is_company = False
        individual_cedula = self.Partner.create({
            'name': 'Pedro Pérez',
            'vat': 'V-12345678',
        })
        self.assertFalse(individual_cedula.is_company)
        self.assertEqual(individual_cedula.company_type, 'person')

