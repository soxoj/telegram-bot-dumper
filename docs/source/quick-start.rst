.. _quick-start:

Quick start
===========

Requirements
------------

- Python >= 3.6
- `Telethon <https://github.com/LonamiWebs/Telethon>`_ (pinned in
  ``requirements.txt``)
- Telegram API credentials — an ``API_ID`` and ``API_HASH`` from a
  `registered Telegram application <https://core.telegram.org/api/obtaining_api_id>`_
  (`my.telegram.org <https://my.telegram.org>`_)

Install
-------

.. code-block:: sh

   pip install -r requirements.txt

The Telegram API credentials are read from the environment — never hard-code
them into the script, which is public:

.. code-block:: sh

   export API_ID=123456
   export API_HASH=abc...

First dump
----------

Point the dumper at a token. By default it walks message ids ``1..∞`` upwards in
batches of 200, downloading every message, all media, and all user profile
photos into a ``<bot_id>/`` directory:

.. code-block:: sh

   ./dumper.py --token 12345678:ABCe2rPVteUWZ7wLeCqCb3CH3ilUY_fLabc

.. note::
   For a **busy** bot the upward walk wastes time on long stretches of pruned
   (deleted/expired) old ids and can give up early. Dumping *downwards* from the
   latest message is far more productive — see :doc:`dumping-modes`.

Once you have a dump, browse it in the :doc:`web viewer <web-viewer>` instead of
reading raw text files.

Run ``./dumper.py --help`` for the full flag list, or see
:doc:`command-line-options`.
