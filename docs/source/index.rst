.. _index:

telegram-bot-dumper
===================

**telegram-bot-dumper** dumps everything reachable through a Telegram **bot
token**: the bot's own profile, the full text history of every chat it has seen,
all message media, and the profiles and photos of the users who talked to it.

**Input:** a bot token, nothing else. **Output:** ``bot.json``, per-chat text
history, downloaded media, and per-user profiles (or a single ``users.csv``).

There are two ways to use it:

- the :doc:`command-line dumper <quick-start>` — one script, one token; and
- the :doc:`web viewer <web-viewer>` — a Telegram-Web-like browser UI over a
  dump, with live streaming and global search.

A faster `Golang port <https://github.com/soxoj/telegram-bot-dumper-go>`_ by
`ScBoln <https://github.com/ScBoln>`_ exists if you prefer a single binary.

.. warning::
   **This tool is intended for authorized security testing and lawful purposes
   only.** A bot token belongs to whoever operates the bot; dumping a bot you
   do not own or have explicit permission to assess may be illegal. Regulations
   on collecting and processing personal data vary by jurisdiction (GDPR, CCPA,
   and others). Ensuring your use is lawful is your responsibility alone, and
   the authors bear no responsibility for misuse.

You may be interested in:
-------------------------
- :doc:`Quick start <quick-start>`
- :doc:`Web viewer <web-viewer>`
- :doc:`Dumping modes <dumping-modes>`
- :doc:`Command-line options <command-line-options>`
- :doc:`Output layout <output-layout>`
- :doc:`How it works <how-it-works>`
- :doc:`FAQ <faq>`
- :doc:`Use case: malware C2 / exfil bot <use-cases/malware-c2>`
- :doc:`Use case: pentesting a leaked bot token <use-cases/pentesting>`

.. toctree::
   :hidden:
   :caption: Getting started

   quick-start
   web-viewer

.. toctree::
   :hidden:
   :caption: Using the dumper

   dumping-modes
   command-line-options
   output-layout

.. toctree::
   :hidden:
   :caption: Reference

   how-it-works
   faq

.. toctree::
   :hidden:
   :caption: Use cases

   use-cases/malware-c2
   use-cases/pentesting

.. toctree::
   :hidden:
   :caption: Contributing

   development
