# Contributing

Thanks for helping! The most valuable contributions right now are **compatibility reports**
from other rekordbox versions and from Windows.

## Compatibility reports

1. Run `rbsync doctor` and `rbsync selftest` (the self test only uses a temporary copy of your
   library).
2. [Open a compatibility report](https://github.com/YasiSaps/rekordbox-playlist-sync/issues/new?template=compatibility.yml)
   and paste both outputs. Remove anything you don't want to share (file paths show your user
   name and track titles).

## Bugs

Please include your OS, rekordbox version, the command you ran and its full output. Never
attach your `master.db`.

## Development

```bash
git clone https://github.com/YasiSaps/rekordbox-playlist-sync
cd rekordbox-playlist-sync
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

- `src/rbsync/planner.py`, `paths.py` and `m3u.py` are pure and fully unit-tested — put logic there.
- `src/rbsync/rekordbox.py` is the only module that touches the database.
- Any change that writes to the database must keep: dry run by default, backup before write,
  refusal while rekordbox is running, and post-write verification.
- To mark a rekordbox version as verified (`TESTED_VERSIONS` in `config.py`), include a passing
  `selftest` **and** a USB check from [docs/TESTING.md](docs/TESTING.md).
