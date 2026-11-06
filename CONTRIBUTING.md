# Contributing

Thanks for helping out. A few things keep this repo easy to maintain.

## Every change needs tests and docs

- **Tests.** Cover what you add or fix with an offline test under `tests/` (no
  token, no network) and make sure the suite stays green:

  ```sh
  pip install -r test-requirements.txt
  pytest tests/ --ignore=tests/bot_test.py
  ```

  `tests/bot_test.py` talks to a real bot and is skipped by default.

- **Docs.** User-facing changes go in `docs/` (the Sphinx site that builds on
  Read the Docs), not only in the commit message. Build it before you push:

  ```sh
  pip install -r docs/requirements.txt
  cd docs && make html
  ```

## Keep the README lean

The README is a landing page: what the tool is, how to install it, and a couple
of examples. Anything longer — every flag, edge cases, use cases — belongs in
`docs/`. If your change makes the README grow, that's usually a sign it should
be a docs page with a one-line pointer from the README instead.

## Pull requests

- Keep each PR to one thing; small PRs get reviewed faster.
- Write commit messages in plain English; match the style already in the log.
- Explain *why* in the PR description, not just *what*.

See `docs/development.rst` for the full development setup.
