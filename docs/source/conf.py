# Configuration file for the Sphinx documentation builder.

import os

# -- Project information

project = 'telegram-bot-dumper'
copyright = '2021-2026, soxoj'
author = 'soxoj'

# No ``release`` / ``version``: the project ships as a single script and has no
# version number to keep in sync. Add both here if that ever changes.

# -- Internationalization
#
# Default to English. Translation projects on Read the Docs set the
# ``READTHEDOCS_LANGUAGE`` env var (e.g. ``zh_CN``); locally the language can be
# overridden via ``sphinx-build -D language=zh_CN``. Mirrors the sibling Maigret
# and socid_extractor docs. No catalogs exist yet -- ``make intl-update
# LANG=<code>`` in docs/ bootstraps one.
language = os.environ.get('READTHEDOCS_LANGUAGE', 'en')
locale_dirs = ['locale/']
gettext_compact = False
gettext_uuid = True

# -- General configuration
#
# Deliberately short: the siblings carry autodoc/autosummary/intersphinx that
# nothing in their .rst files ever calls. Add an extension when a page needs it.

extensions = [
    'sphinx.ext.duration',
    'sphinx_copybutton',
]

templates_path = ['_templates']

# -- Options for HTML output

html_theme = 'sphinx_rtd_theme'

# -- Options for EPUB output
epub_show_urls = 'footnote'
