{
    'name': 'SolviTask',
    'version': '17.0.3.0.0',
    'summary': 'Plumbing & heating service management',
    'description': 'Customers, plumbers, jobs, services, tools and materials.',
    'category': 'Services',
    'author': 'Author',
    'website': 'Website',
    'depends': ['base', 'web'],
    'assets': {
        'web.assets_backend': [
            'solvitask/static/src/scss/solvitask.scss',
            'solvitask/static/src/js/wrapper.js'
        ]
    },
    'data': [
        'security/solvitask_security.xml',
        'security/ir.model.access.csv',
        'report/job_invoice_report.xml',
        'views/menus.xml',
        'views/customer_view.xml',
        'views/plumber_view.xml',
        'views/service_view.xml',
        'views/tool_view.xml',
        'views/material_view.xml',
        'views/job_view.xml',
        'views/requests_view.xml',
        'views/service_request_view.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
