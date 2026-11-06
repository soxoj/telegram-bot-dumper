.. _output-layout:

Output layout
=============

Everything a run produces lands under a single directory named after the bot's
numeric id (the part of the token before the ``:``)::

   <bot_id>/
   ├── <bot_id>.session          # Telethon session (reused across runs)
   ├── bot.json                  # the bot's own profile + the token
   ├── last_message_id.txt       # last id seen in live mode (resume hint)
   ├── users.csv                 # only with --users-csv (see below)
   └── <chat_id>/                # one directory per chat / user the bot has seen
       ├── <chat_id>.json        # the user's full profile
       ├── <chat_id>_history.txt # text history for this chat
       ├── <photo_id>.jpg        # the user's profile photos (avatars)
       └── media/                # media sent inside messages
           ├── <photo_id>.jpg
           └── <filename>        # documents, voice, video, ...

Re-running against a token whose ``<bot_id>/`` already exists **rotates** the old
directory to ``<bot_id>_<timestamp>/`` and starts fresh, copying the existing
``.session`` forward so you don't re-authenticate.

Text history format
-------------------

Each line in ``<chat_id>_history.txt`` is one message. The tag prefix records who
sent it and where:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Line shape
     - Meaning
   * - ``[id][from_id][date] text``
     - Incoming private message from a user.
   * - ``[id][from_id][to:chat_id][date] text``
     - Outgoing message the **bot** sent to a user.
   * - ``[id][from:user][group:chat][date] text``
     - A message inside a group / supergroup.

Media inside a message is written as a reference into the same line, e.g.
``Photo: media/<id>.jpg`` or ``Document: media/<filename>`` — pointing at the
``media/`` directory beside the history file. With ``--no-media`` the reference
is kept but marked ``(skipped)`` and nothing is downloaded.

``users.csv``
-------------

With ``--users-csv`` the per-user JSON directories are replaced by one
``<bot_id>/users.csv`` with columns::

   id, username, first_name, last_name, phone, lang_code,
   bot, premium, verified, scam, fake

This is the lightest output — pair it with ``--no-photos --no-media
--no-history`` for a pure roster of who has talked to the bot.
