# Deploying spectra_inspector

How to run the stack on a server with `./start_docker.sh prod`: the two app
containers behind a [Caddy](https://caddyserver.com) reverse proxy that
terminates TLS with a Let's Encrypt certificate and restricts access. For
development, and for the `.env` files both modes need, see the
[README](README.md).

## What `prod` runs

`prod` layers `compose.prod.yaml` on `compose.yaml` and starts the stack
detached:

- The only host endpoints are ports 80 and 443 of the `caddy` service. Neither
  app container publishes a port: caddy forwards to the frontend as
  `frontend:8050` over the compose network, and the frontend reaches the backend
  the same way. Caddy applies no response timeout and no request body limit,
  which the frontend needs (backend operations may run for two minutes and Dash
  callbacks upload the figure state).
- The frontend is served by gunicorn (`SPECTRA_INSPECTOR_N_FRONTEND_WORKERS`
  worker processes, four threads each) rather than the flask development server
  that `serve.py` and the development overlay use. Set
  `SPECTRA_INSPECTOR_N_FASTAPI_WORKERS` in the backend `.env` to run more than
  one uvicorn worker.
- Both app containers run as the image's non-root user, so the data root must be
  world-readable (`chmod -R a+rX` on the host directory; `rsync -a` from a
  laptop preserves whatever restrictive modes the source had). It is mounted
  read-only.
- Every service restarts on failure and after a host reboot
  (`restart: unless-stopped`; the docker daemon must itself be enabled at boot,
  `systemctl is-enabled docker`), and caps its json log files at three times 10
  MB.
- The backend has a health check against `/info`; the frontend waits for it. The
  startup scan of the data root counts against a two minute grace period.

## Prerequisites

- A host with docker and the compose plugin, and a user in the `docker` group.
- A DNS name for the host that resolves to its public address, with ports 80 and
  443 reachable from the internet. Let's Encrypt validates from several
  locations, so a campus firewall that only admits campus traffic blocks
  issuance and renewal both.
- The data tree on the host, readable by everyone (see above). Its path must
  exist before the first `up`, otherwise docker creates an empty root-owned
  directory there and the backend reports no datasets.
- Both `.env` files (README, "Initialize configuration"). The two that matter
  for deployment are in `packages/spectra_inspector_server/.env`:
  `SPECTRA_INSPECTOR_HOST_DATA_ROOT` is the tree's path on the host and
  `SPECTRA_INSPECTOR_DATA_ROOT` where it appears inside the container. The
  frontend `.env` can stay as the template: compose overrides the server host
  and write dir inside the container.

## Running compose by hand

`start_docker.sh` and `stop_docker.sh` pass both `.env` files and both compose
files to `docker compose`, and so does `compose.sh prod`, which takes any
compose command. A bare `docker compose` lacks the `.env` files that supply the
`${...}` values in `compose.yaml` and stops with
`required variable SPECTRA_INSPECTOR_HOST_DATA_ROOT is missing a value`. The
rest of this document uses the wrapper:

```sh
./compose.sh prod ps            # state of the three services
./compose.sh prod logs -f caddy # or fastapi, frontend, or nothing for all three
```

## The Caddyfile

`proxy/Caddyfile` is untracked and holds everything deployment-specific:

```sh
cp proxy/Caddyfile.example proxy/Caddyfile
```

The template has three numbered spots to edit: the e-mail address Let's Encrypt
sends expiry warnings to, the site's host name, and access control. Access
control is two layers, each removable on its own:

- An allowlist of client address ranges; everything else gets `403`. Ask IT for
  the authoritative ranges for your institution and its VPN.
- HTTP basic auth, one `user hash` line per account. The template ships with the
  hash of `change-me`; replace it before going live:
  ```sh
  docker run --rm -it caddy:2-alpine caddy hash-password
  ```
  It prompts for the password (hence `-it`) and prints the hash.

An `X-Robots-Tag: noindex` header and a deny-all `robots.txt` are served
regardless. Check the file after editing:

```sh
docker run --rm -v ./proxy/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2-alpine \
    caddy validate --config /etc/caddy/Caddyfile
```

## First start and the certificate

Caddy obtains the Let's Encrypt certificate for the host name on first start and
renews it on its own. Let's Encrypt allows 5 certificates per week for the same
name, so do the first start against the staging CA, which issues certificates
browsers do not trust but has generous limits:

1. In `proxy/Caddyfile`, uncomment the `acme_ca` staging line. The basic auth
   placeholder can stay for this test.
2. `./start_docker.sh prod`, then `./compose.sh prod logs -f caddy`. Within a
   minute you want `certificate obtained successfully` with the staging issuer.
   Repeated `challenge failed` errors mean DNS or port reachability.
3. Open the site, click through the untrusted-issuer warning, log in as
   `spectra` / `change-me`, and check that data loads.
4. Set the real basic auth line, comment the `acme_ca` line out again, validate,
   then remove the staging certificate and restart. The certificate lives in the
   `caddy_data` volume, which `stop_docker.sh` deliberately leaves in place, so
   it has to go by hand:
   ```sh
   ./stop_docker.sh prod
   docker volume ls | grep caddy          # spectra_inspector_caddy_data
   docker volume rm spectra_inspector_caddy_data
   ./start_docker.sh prod
   ./compose.sh prod logs -f caddy        # issuer now acme-v02, not staging
   ```

That last start is the one issuance that counts against the weekly limit.

## Updating a running deployment

Nothing below re-issues the certificate. It is only re-issued when the
`caddy_data` volume is removed, the host name in the Caddyfile changes, or the
renewal window arrives (Caddy handles that one).

**New code.** Fetch, check out what you want to run, and start. No stop step:
`start_docker.sh` runs `compose up --build --detach`, which rebuilds the two app
images and recreates only the containers whose image or configuration changed.
Caddy keeps running throughout, so the site answers the whole time, with a
minute or two of `502` while the backend passes its health check and the
frontend comes up behind it.

```sh
git fetch --tags
git checkout v0.1.0        # a release tag, or `main` and `git pull`
./start_docker.sh prod
./compose.sh prod ps
```

Pinning to a tag rather than `main` means a later merge does not change what the
next `git pull` deploys, and rolling back is the same three commands with the
previous tag. The untracked `.env` files and `proxy/Caddyfile` survive the
checkout.

**A `.env` change.** The files are handed to the containers at start, not baked
into the images, so re-run `./start_docker.sh prod`; compose sees the changed
environment and recreates the affected container. Changing
`SPECTRA_INSPECTOR_HOST_DATA_ROOT` moves the bind mount, so the new path must
exist and be readable first.

**A Caddyfile change** (accounts, allowlist):

```sh
docker run --rm -v ./proxy/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2-alpine \
    caddy validate --config /etc/caddy/Caddyfile
./compose.sh prod restart caddy
```

**More data.** Copy into the data root on the host, `chmod -R a+rX` it, then
restart the backend so it rescans: `./compose.sh prod restart fastapi`.
Alternatively set `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH=true` and use the refresh
button, at the cost of letting any logged-in user trigger a full rescan.

**Stopping.** `./stop_docker.sh prod` removes the containers and keeps the
images, the data directory, the result cache and the caddy volumes. The host
reboot case needs nothing: every service has `restart: unless-stopped`.

## The result cache

The first thing every user does with a sample is load its full spectrum and the
full-extent images of the default element windows, each a pass over the whole
cube. With `SPECTRA_INSPECTOR_RESULT_CACHE_DIR` set in the backend `.env` the
backend keeps those results on disk and answers repeat requests from there;
zoomed, boxed and polygon selections are always computed. The cache directory
mirrors the data tree (the entries for `<data_root>/a/b/map123_0.spd` are under
`<cache_dir>/a/b/map123_0/`), each entry is a `.npz` keyed on the `.spd` file's
modification time and size so a replaced file is a miss rather than a stale
result, and nothing in it is ever deleted by the backend. Budget about 50 MB per
map.

In compose that host directory is bind-mounted at the same path inside the
container, so one absolute path configures both docker and a backend run outside
it. Like the data root it must exist before the first `up`, or docker creates it
root-owned. The backend runs as uid 999, so entries written on the host must be
readable by that uid, and the directory must be writable by it for the backend
to add entries on a miss (`chown -R 999 <cache_dir>` or `chmod -R a+rwX`). An
unwritable directory only disables filling; a missing or unreadable entry is
recomputed. The cache can share a filesystem with the data, for instance as a
sibling of the data root, but not live inside it.

Fill the cache ahead of time with `scripts/precompute_result_cache.py`, which
walks the data root with the same scan the backend uses and writes the spectrum
and the default element images (Mg, Al and Si, override with `--elements`) for
every map. Pass `--allow-mixed-basenames` if the backend `.env` sets
`SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES=true`, since it decides which
filesets exist. Entries that are already up to date are skipped and the script
only ever adds entries, so it is safe to run against a live backend, off-hours,
with no downtime:

```sh
cd packages/spectra_inspector_server
uv run python ../../scripts/precompute_result_cache.py /path/to/data_root /path/to/result_cache
```

It can equally run on a laptop and the result be copied next to the data:
`rsync -a` preserves the modification times the entries are keyed on, and the
relative layout matches by construction, so a cache built against a copy of the
data tree is valid on the host as long as the copy was made with `rsync -a` too.
