.. _how-it-works:

How it works
============

Walking message ids
-------------------

A bot cannot ask Telegram "give me my last N messages" the way a user client
can. What it *can* do is fetch messages by **id** with ``messages.getMessages``.
So the dumper walks the id space in batches (200 by default), fetching each
batch and writing out whatever comes back. Ids that were never used, or whose
messages were deleted or expired, come back as ``MessageEmpty`` and are skipped.

- **Upwards** (default) starts at id 1 and climbs. Simple, but it burns through
  long runs of empty low ids on a busy bot.
- **Downwards** (``--down``) first probes for the highest live id (trying powers
  of 10 up to 10⁹), then walks down from there. Far more productive on an active
  bot.

An all-empty batch normally ends the walk. ``--lookahead N`` keeps it scanning
``N`` more batches past the gap, for histories that are sparse but not finished.

.. note::
   **Telegram does not keep bot history forever.** Empirically only the last few
   hundred thousand messages stay reachable — in testing a busy bot exposed
   roughly the last **500K** before ``messages.getMessages`` returned only
   ``MessageEmpty`` for older ids. If a bot has processed more traffic than that,
   the older history is gone server-side and no flag will bring it back.

Resolving users
---------------

For every message, the dumper resolves the other party's profile — for
**incoming** messages *and* for the bot's **outgoing** replies — via
``users.getFullUser``, saving the profile and (unless ``--no-photos``) their
avatars. Each user is resolved once per run.

Groups and privacy mode
-----------------------

``messages.getMessages`` only returns the bot's **private** message history.
Basic-group and supergroup history needs per-channel calls that bots generally
can't make, so it is **not** dumped by the id walk.

Groups are reachable **live** instead. If the bot has been added to a group or
supergroup **and** its
`privacy mode <https://core.telegram.org/bots/features#privacy-mode>`_ is
**disabled**, it receives *all* group messages — not just commands and replies —
and ``--listen-only`` captures them in real time. With privacy mode enabled (the
default) the bot only sees commands, mentions, and replies. Group messages in the
history are tagged ``[from:USER][group:CHAT]`` (see :doc:`output-layout`).

Known limits
------------

- **A run can stop before the history is fully dumped.** A batch that comes back
  entirely empty — because users deleted their messages, or because old ids were
  pruned server-side — can end the walk early. Raise ``--lookahead`` to scan past
  empty stretches, or prefer ``--down``, which is much less affected by gaps.
- **Group / supergroup *history* is not dumped**, only captured live (see above).
