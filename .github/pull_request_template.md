## What does this change?

## How was it tested?
- [ ] `pytest`
- [ ] `rbsync selftest` (OS / rekordbox version: )

## Safety checklist (for changes that write to the database)
- [ ] Dry run stays the default
- [ ] Backup is made before any write
- [ ] Still refuses to write while rekordbox is running
- [ ] Result is verified after writing
