.. _web-viewer:

Web viewer
==========

A **Telegram-Web-like browser UI for a dump**: a chat list, full message history
with inline media, user profiles with a photo carousel, and global search across
every conversation at once.

**Live mode** is supported: the viewer runs the dumper in the background and
streams new messages into the browser in real time.

.. image:: webapp-corporate.png
   :alt: Web viewer showing the dump of an internal corporate bot
   :width: 100%

You log in with the bot token, which must match the one saved in that dump's
``bot.json``; the session cookie then guards every request. Read-only viewing
needs **no** API credentials — only live capture does.

From an open chat, **Download chat** saves its history, media, and photos as
``dump_<bot_id>_<chat_id>.zip`` (other chats and bot-level files excluded), and
**Export links** saves every URL across the dump with its sender id as a CSV.

.. _viewer-quick-start:

Quick start
-----------

Run the viewer with live mode and dumping of new bots, without Docker:

.. code-block:: sh

   pip install -r requirements.txt
   cp .env.example .env      # fill in API_ID and API_HASH from https://my.telegram.org
   ./run-viewer.sh

Open http://127.0.0.1:8010 and paste a bot token. A bot that already has a dump
opens it; a new bot gets its folder and ``bot.json``. Either way live mode starts
right after login: the viewer dumps the history it doesn't have yet and then shows
new messages as they arrive.

``run-viewer.sh`` reads ``API_ID``, ``API_HASH`` and the optional ``PORT`` /
``HOST`` from ``.env`` and starts ``webapp/server.py --allow-new-dumps``. Extra
arguments are passed on, so ``./run-viewer.sh ~/dumps`` serves another folder.
By default it listens on ``127.0.0.1`` only; see :ref:`new-dumps` before exposing it.

Run from a prebuilt image (Docker Hub)
--------------------------------------

.. code-block:: sh

   docker run --rm -p 127.0.0.1:8010:8010 -v "$PWD:/data" soxoj/telegram-bot-dumper-web

Build locally
-------------

.. code-block:: sh

   docker compose up --build      # builds and serves on http://127.0.0.1:8010

Without Docker
--------------

.. code-block:: sh

   pip install -r requirements.txt
   python webapp/server.py        # serves dumps from the repository folder on :8010
   python webapp/server.py ~/dumps  # or from another folder

Open http://127.0.0.1:8010 and paste a bot token to pick its dump folder.

Live mode
---------

Live mode additionally needs ``API_ID`` / ``API_HASH`` from
`my.telegram.org <https://my.telegram.org>`_, passed **via the environment** —
never baked into the image:

.. code-block:: sh

   # one-off container
   docker run --rm -p 127.0.0.1:8010:8010 -v "$PWD:/data" \
     -e API_ID=123456 -e API_HASH=abc... soxoj/telegram-bot-dumper-web

   # or with docker compose: put them in a local .env (see .env.example)
   cp .env.example .env && $EDITOR .env && docker compose up

   # or without Docker
   API_ID=123456 API_HASH=abc... python webapp/server.py

Configuration
-------------

.. list-table::
   :header-rows: 1
   :widths: 20 30 50

   * - Variable
     - Default
     - Effect
   * - ``PORT``
     - ``8010``
     - Port the viewer listens on.
   * - ``HOST``
     - ``127.0.0.1``
     - Bind address. Set ``0.0.0.0`` to expose it (the Docker image already does).
   * - ``API_ID`` / ``API_HASH``
     - *(unset)*
     - Telegram API credentials. Only needed for live capture; viewing an
       existing dump needs neither.
   * - ``ALLOW_NEW_DUMPS``
     - *(unset)*
     - Set ``1`` (CLI ``--allow-new-dumps``) to let a token with no dump yet be
       dumped from the login screen. Needs ``API_ID``/``API_HASH``.
   * - ``ALLOW_PUBLIC``
     - *(unset)*
     - Set ``1`` (CLI ``--allow-public``) to allow ``ALLOW_NEW_DUMPS`` on a
       non-loopback ``HOST``. Without it the server refuses to start in that case.

.. _new-dumps:

Dumping a new bot from the viewer
---------------------------------

By default the viewer only opens bots that already have a dump; pasting an
unknown token just says there is no dump for it. With ``ALLOW_NEW_DUMPS`` on,
an unknown token is instead checked with Telegram, the bot gets its folder and
``bot.json``, and live mode dumps its whole history straight into the browser.

.. warning::
   This lets anyone who can open the page dump any bot under **your**
   ``API_ID``. The viewer therefore refuses to start with ``ALLOW_NEW_DUMPS``
   on a non-loopback ``HOST`` unless you also set ``ALLOW_PUBLIC=1``. The Docker
   image binds ``0.0.0.0`` inside the container, so keep the published port on
   ``127.0.0.1`` (as the ``docker run`` lines above do) and treat
   ``ALLOW_PUBLIC`` as a deliberate choice.

.. code-block:: sh

   docker run --rm -p 127.0.0.1:8010:8010 -v "$PWD:/data" \
     -e API_ID=123456 -e API_HASH=abc... -e ALLOW_NEW_DUMPS=1 -e ALLOW_PUBLIC=1 \
     soxoj/telegram-bot-dumper-web

Without Docker, ``./run-viewer.sh`` from the :ref:`quick start <viewer-quick-start>`
does the same, or pass the flag yourself:
``API_ID=123456 API_HASH=abc... python webapp/server.py --allow-new-dumps``.
