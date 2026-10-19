# Privacy and local storage

The application runs on localhost and does not ask for API keys or brokerage credentials.
Its browser code requests only local application endpoints. Rule-source links open the
referenced providers only when followed. There is no analytics service or remote AI call.

- `data/` contains local imported databases and import metadata.
- `sessions/` contains local attempts, journal text and rewind archives.
- These folders, `.env` files, virtual environments and model weights are excluded by
  `.gitignore`. Ignoring files does not protect files that someone explicitly force-adds.
- The server exposes a fixed list of frontend assets and local APIs, not arbitrary files.
- Do not expose the server through public tunnels or port forwarding.
- Do not share session files or diagnostic logs without reviewing their contents.

The bundled CSVs contain only timestamp, open, high, low, close and volume columns.
They contain no account/trade history, usernames, download URLs or provider request metadata.
Application licensing does not grant additional rights to third-party market data.

A public GitHub repository displays its owner's username and public commit metadata.
This release uses a GitHub noreply commit address. Other private repositories, their
history and Git configuration are not included. Public readers can download or fork
this code; they cannot push to the owner's repository without write permission.

Before publishing updates, stage only intended files and run `python3 check_release.py`.
Review the staged diff too. Pattern scans are useful checks, not proof that every
possible secret or security vulnerability has been ruled out.
