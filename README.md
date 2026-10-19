# Lucid Practice

Local manual futures replay for practicing execution, reviewing habits, and understanding risk. No broker connection, automated trading bot, private weights, telemetry, or private account data. This tool cannot guarantee that you will avoid losses.

## Download and run locally

This is a standalone **manual replay simulator**, not a live trading bot. No API keys,
broker login, paid AI service, Node installation, or cloud server are needed to run it.

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/).
   On Windows, enable the Python launcher during installation.
2. On this repository's GitHub page, choose **Code → Download ZIP** and extract it.
3. Open Terminal (macOS/Linux) or PowerShell (Windows) inside the extracted folder.
   The folder must contain `server.py`.

**macOS / Linux**

```sh
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install tzdata
.venv/bin/python server.py
```

**Windows PowerShell**

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install tzdata
.\.venv\Scripts\python.exe server.py
```

Open **http://127.0.0.1:8766** in your browser. Leave the terminal running.
Press **Ctrl+C** in that terminal to stop the server. Run the same final command
again to resume later; your attempts remain stored locally.

The first launch imports the bundled candles into a local SQLite database. Python's
standard library provides the application dependencies; `tzdata` supplies Chicago
session timezones on machines without system timezone data. Installing Python and
`tzdata` needs internet access; replay itself does not.

Choose **Sessions**, select personal practice or an account-rule simulation, then
start a randomized day/time or choose a recorded time manually. Use **Play** or
**Step**, choose a quantity, and submit simulated **Mkt Buy / Mkt Sell** orders.
TP/SL is optional in warning-only personal practice; enforced risk/challenge modes
require stops. **Next trading day** preserves the account and advances to the next
recorded **5 p.m. America/Chicago** open (CST/CDT). Close positions and cancel pending
orders first. Missing overnight data produces an explanation instead of invented candles.
A failed challenge stops the attempt and opens **Journal**. Save a reason for each
trade and review its costs and exit; consistency alone does not establish a pass.

See [sample data details](sample_data/README.md) for provenance and scope.

### Troubleshooting

- **Python not found:** install Python, reopen the terminal, and check the version.
  On Windows use `py -3`; on macOS/Linux use `python3`.
- **Cannot find server.py:** change directory to the extracted project folder.
- **Timezone / ZoneInfo error:** install `tzdata` using the virtual-environment Python
  shown above, then restart.
- **Port already in use:** stop the earlier server, or append `--port 8771` to the
  launch command and open http://127.0.0.1:8771 instead.
- **Browser cannot connect:** keep the terminal running and use the exact local
  address printed there. Do not use HTTPS for this local server.
- **No later session:** the imported archive has no eligible later 5 p.m. open.
  Import more one-minute candles or start another recorded attempt.
- **Incomplete import:** preserve the original files and error message; do not
  delete your sessions to troubleshoot.

You can ask an AI assistant for help: “I am running Lucid Practice locally on
[operating system], using Python [version]. I ran [command] and received [error].
Help me diagnose it without deleting my saved sessions.” Remove usernames, local
personal paths, credentials, account information, and private trade notes before
sharing logs. Never provide API keys, passwords, `.env` files, or your entire home
folder. You can also report a reproducible issue here with sanitized details.

### Import your own candles

To add other licensed **one-minute** CSV files:

```sh
python3 import_csv.py --nq /path/to/NQ.csv --es /path/to/ES.csv --name my-history
python3 server.py
```

Open http://127.0.0.1:8766 and choose **Sessions**.

CSV columns: `ts_event,open,high,low,close,volume`. Timestamps must include a timezone and represent candle opens aligned to whole minutes. Optional `contract` identifies the contract. Never label five-minute data as one-minute. Malformed values and duplicate timestamps are rejected. Gaps remain gaps. Each import requires a new name; old data is preserved.

Automatic selection requires a complete Chicago regular session and preceding candle. Partial days can be selected manually where both symbols have the required current/preceding bars.

The server binds only to loopback. Data and sessions stay on your computer. Do not expose it through tunnels, port forwarding, or public bind addresses.

## Navigation

- **Replay**: charts, direct simulated Buy/Sell, optional brackets, and Flatten.
- **Journal**: completed trades, net expectancy, profit factor, and trade review.
- **Risk**: risk per trade, overall loss allowance, and contract cap. No-stop practice requires warning-only mode; challenges retain enforcement.
- **Sessions**: local data, starting dates, and saved attempts.
- **Help**: shortcuts and execution assumptions.

Repeated same-direction clicks accumulate exposure within caps. Opposing clicks reduce an open position up to flat; oversized reversals are rejected. Brackets apply to new entries. Orders fill at the next source-bar open, not tick-by-tick. Stops win ambiguous same-bar touches. Gap losses can exceed planned risk. Missing execution data halts replay. Costs include fees and configured slippage. NQ/ES prices are proxies for micro contracts. Winning backtests do not establish an edge.

## Privacy

Private datasets, sessions, environment files, credentials, databases, and weights are ignored. The server serves an explicit asset allowlist. Never force-add private files. Begin with fresh repository history; do not import the private bot repository, history, or submodules.

Tests: `python3 -m unittest discover -p 'test_*.py'`. JavaScript syntax: `node --check app.js` and `node --check chart.js`.

## Owner control

The public repository should have only its owner with write access. No collaborators, write teams, or write-capable automation. People can submit pull requests, but the owner chooses what to merge. Public users can maintain their own forks; that does not give them access to update the original repository.

Application code is MIT licensed. Third-party market data is not relicensed by the application license.

### Replay and review

The replay bar includes Back (one source candle), Play/Pause, Step, speed, and Date/session. A separate highlighted row contains Next trading day.
Back is available only for steps recorded by this version. It restores the saved account and
price clock, and preserves the abandoned state under the local session's `.replay-history`
folder. Attempts that use it are visibly marked **Rewound practice**: their results are not
unseen forward tests. Saved review notes and layout settings remain current.

The account strip shows cash distance to the personal floor (excluding open P&L), together
with whether personal limits are enforced. Journal includes a locally saved session review.
The position row includes last price and a next-open Close position action.
