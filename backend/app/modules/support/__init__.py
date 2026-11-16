"""support schema - durable support-ticket rows and their email outbox.

Owned solely by this module (app/modules/api/v1/support.py is the only
writer, via app.modules.support.service) - the cross-module
no-direct-writes rule applies here exactly as everywhere else.
"""
