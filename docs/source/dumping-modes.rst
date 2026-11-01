.. _dumping-modes:

Dumping modes
=============

The dumper reads a bot's history by asking Telegram for messages by **id**.
Which direction it walks those ids, and where it starts, is the main thing you
tune per run.

Upwards (default)
-----------------

Walks ids ``1..∞`` upwards in batches of 200, downloading everything:

.. code-block:: sh

   ./dumper.py --token TOKEN

Best for a bot with a **short** history. For a busy bot it wastes time on long
stretches of pruned old ids and may stop early — use ``--down`` instead, or bump
``--lookahead`` to scan past the gaps.

Downwards from the latest message
---------------------------------

``--down`` auto-probes the upper bound (powers of 10 up to 10⁹) and starts from
the highest non-empty id it finds, walking down:

.. code-block:: sh

   ./dumper.py --token TOKEN --down

This is the productive mode for an active bot, and it is much less affected by
gaps in old ids.

Start from a known id
---------------------

If you already know a recent message id (e.g. one you saw live), skip the probe
and start exactly there:

.. code-block:: sh

   ./dumper.py --token TOKEN --start-from-id 11922524

Listen mode
-----------

Don't dump anything; just watch what arrives. On the first incoming message the
script offers to start a downward dump from that id:

.. code-block:: sh

   ./dumper.py --token TOKEN --listen-only

Listen mode is also how **group messages** are captured — see
:doc:`how-it-works`.

Lightweight user enumeration
----------------------------

When you only need a roster of who has talked to the bot — no zips, no jpegs, no
per-chat history — combine the skip flags with ``--users-csv``:

.. code-block:: sh

   ./dumper.py --token TOKEN --down --users-csv --no-photos --no-media --no-history

Output is a single ``<bot_id>/users.csv`` (see :doc:`output-layout`).

Tuning the batch size
---------------------

Smaller batches give faster feedback in the log and a shorter recovery window
after a `FloodWait <https://docs.telethon.dev/en/stable/concepts/errors.html>`_;
larger batches mean fewer round-trips when scanning sparse / pruned id ranges.
Values up to ``1000`` work fine in practice:

.. code-block:: sh

   ./dumper.py --token TOKEN --down --batch-size 50
   ./dumper.py --token TOKEN --down --batch-size 1000

Resuming after a crash or FloodWait
-----------------------------------

The downward walk prints ``Requesting message ids X..Y ...`` for every batch. If
a run is interrupted, restart from the last printed lower bound:

.. code-block:: sh

   ./dumper.py --token TOKEN --start-from-id <Y>

In live mode the last observed id is also written to
``<bot_id>/last_message_id.txt``.

Routing through Tor
-------------------

``--tor`` routes through a local Tor SOCKS5 proxy on ``127.0.0.1:9050``, to
bypass Telegram blocking:

.. code-block:: sh

   ./dumper.py --token TOKEN --tor
