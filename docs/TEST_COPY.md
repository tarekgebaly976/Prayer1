# Test copy (on the same server)

A second, separate installation of the CMMS on the same server, for training and for trying things out
without touching the real data.

| | Real system | Test copy |
|---|---|---|
| Address | `https://<domain>` | `https://test.<domain>` |
| Database and attachments | real | separate copy, taken from the real data when started or refreshed |
| Screen | normal | red **TEST** label at the bottom of every page |
| E-mail | sent | never sent |
| Integration tokens | kept | deleted in the copy, so no plant system can write to it |

Users sign in to the test copy with the same e-mail and password they had on the real system on the day of the copy.

## Commands (on the server)

```
cd /opt/cmms
sudo bash scripts/test-copy.sh start     # create it from the real data, or start it again
sudo bash scripts/test-copy.sh refresh   # discard all test changes and copy the real data again
sudo bash scripts/test-copy.sh stop      # stop it, keep its data
sudo bash scripts/test-copy.sh remove    # delete it and its data
sudo bash scripts/test-copy.sh status
```

The first time, update the real system first (`sudo git pull && sudo bash deploy/install-server.sh`): it adds the
private network the test copy is reached through.

## How it is isolated

- Its own Docker Compose project (`papermill-cmms-test`), its own PostgreSQL container with its own passwords
  (`deploy/.env.test`, generated, mode 600) and its own volumes. `refresh` and `remove` delete only those.
- The real database is only read, with `pg_dump`; the real system keeps running while the copy is made.
- The main Caddy serves `test.<domain>` and forwards it to the test containers over the `papermill-cmms-edge`
  network. While the copy is stopped, that address answers 502.
- It runs the same version (the same images) as the real system. Nightly backups cover the real system only.
