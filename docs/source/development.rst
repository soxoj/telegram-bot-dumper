.. _development:

Development
===========

The project is a single script (``dumper.py``) plus a small web viewer
(``webapp/``). No package, no build step.

Tests
-----

Offline unit tests run with no network and no token:

.. code-block:: sh

   pip install -r test-requirements.txt
   pytest tests/ --ignore=tests/bot_test.py

The integration test in ``tests/bot_test.py`` talks to a **real** bot and needs
a working token:

.. code-block:: sh

   TEST_TOKEN=12345678:... pytest tests/bot_test.py

Building these docs
-------------------

.. code-block:: sh

   pip install -r docs/requirements.txt
   cd docs && make html          # output in docs/build/html

The docs mirror the sibling `Maigret <https://maigret.readthedocs.io>`_ and
socid_extractor setup: Sphinx with the Read the Docs theme, published on Read
the Docs via ``.readthedocs.yaml``. A translation pipeline (``make gettext`` /
``make intl-update LANG=<code>`` / ``make html-<code>``) is wired up in
``docs/Makefile`` but no catalogs exist yet.
