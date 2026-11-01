.. _command-line-options:

Command-line options
=====================

The authoritative list is ``./dumper.py --help``; this page mirrors it.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Flag
     - Effect
   * - ``--token TOKEN``
     - Telegram bot token to dump. If omitted, the script prompts for one.
   * - ``--down``
     - Walk message ids downwards, auto-probing the max id when
       ``--start-from-id`` is not set. Best for active bots.
   * - ``--start-from-id N``
     - Dump downwards starting from message id ``N`` (skips the probe).
   * - ``--resume``
     - Continue an interrupted downward dump from the id saved in
       ``last_message_id.txt``, keeping the existing folder and history.
   * - ``--listen-only``
     - Don't dump history; watch for new messages in real time. On the first one,
       offers to start a downward dump from its id.
   * - ``--batch-size N``
     - Number of message ids requested per cycle (default ``200``; up to ``1000``
       works in practice).
   * - ``--lookahead N``
     - After an all-empty batch, keep scanning ``N`` more batches before giving
       up. Useful when ids are sparse.
   * - ``--no-photos``
     - Skip downloading user profile photos (avatars).
   * - ``--no-media``
     - Skip downloading photos and documents inside messages; metadata is still
       written to the text history.
   * - ``--no-history``
     - Don't write per-chat ``<chat_id>_history.txt``. Combine with
       ``--users-csv`` for the lightest possible run.
   * - ``--users-csv``
     - Write users to a single ``<bot_id>/users.csv`` instead of
       ``<user_id>/<user_id>.json`` directories.
   * - ``--tor``
     - Route through a local Tor SOCKS5 proxy on ``127.0.0.1:9050``.
   * - ``--output DIR``
     - Directory to save the dump (default ``./<bot_id>``).
   * - ``--no-listen``
     - Exit after dumping history instead of listening for new messages.

Credentials are **not** flags: ``API_ID`` and ``API_HASH`` are read from the
environment (see :doc:`quick-start`).
