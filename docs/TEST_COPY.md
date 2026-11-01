# Test copy (on the same server)

A second, separate installation of the CMMS on the same server, for training and for trying things out
without touching the real data.

| | Real system | Test copy |
|---|---|---|
| Address | `https://<domain>` | `https://test.<domain>` |
| Database and attachments | real | separate copy, taken from the real data when started or refreshed |
| Screen | normal | red **TEST** label at the bottom of every page, red **TEST** icon, tab title starts with "TEST ·" |
| Version | the installed one | its own: the same as the real system, or a newer one being tried (`update`) |
| E-mail | sent | never sent |
| Integration tokens | kept | deleted in the copy, so no plant system can write to it |

Users sign in to the test copy with the same e-mail and password they had on the real system on the day of the copy.

## Commands (on the server)

```
cd /opt/cmms
sudo bash scripts/test-copy.sh start     # create it from the real data, or start it again
sudo git pull && sudo bash scripts/test-copy.sh update   # try the new version in the test copy ONLY
sudo bash scripts/test-copy.sh same-as-real              # test copy back to the real system's version
sudo bash scripts/test-copy.sh refresh   # discard all test changes and copy the real data again
sudo bash scripts/test-copy.sh stop      # stop it, keep its data
sudo bash scripts/test-copy.sh remove    # delete it and its data
sudo bash scripts/test-copy.sh status    # also shows which version each one runs
```

## Trying a new version before the users see it

1. `cd /opt/cmms && sudo git pull` – downloads the new code. The real system does not change: it keeps running the
   version it was built with.
2. `sudo bash scripts/test-copy.sh update` – builds the new code for the test copy only and updates the test copy's
   database. Try it at `https://test.<domain>`.
3. Good → `sudo bash deploy/install-server.sh` updates the real system to the same version.
   Not good → `sudo bash scripts/test-copy.sh same-as-real` and report the problem; the users never saw it.

Do not run `deploy/install-server.sh` before you are happy with the test: that is the step that updates the real system.

The first time, update the real system first (`sudo git pull && sudo bash deploy/install-server.sh`): it adds the
private network the test copy is reached through.

## How it is isolated

- Its own Docker Compose project (`papermill-cmms-test`), its own PostgreSQL container with its own passwords
  (`deploy/.env.test`, generated, mode 600) and its own volumes. `refresh` and `remove` delete only those.
- The real database is only read, with `pg_dump`; the real system keeps running while the copy is made.
- The main Caddy serves `test.<domain>` and forwards it to the test containers over the `papermill-cmms-edge`
  network. While the copy is stopped, that address answers 502.
- It runs the same version (the same images) as the real system. Nightly backups cover the real system only.
