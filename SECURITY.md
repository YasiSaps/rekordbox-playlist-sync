# Security and data safety

rbsync runs locally and never sends data anywhere. It reads and writes only the rekordbox
library database and its own backup/log folder (`Documents/rbsync`, or `RBSYNC_HOME`).

If you find a way rbsync could damage a library, delete files, or behave unsafely, please report
it privately via **GitHub → Security → Report a vulnerability** on this repository rather than in
a public issue.
