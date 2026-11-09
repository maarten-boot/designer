# Pinning what the workflows run

The user's rule (turn 206): pin every action step on its hash and use the
latest workable version, and say where that is not possible. Applied to
`.github/workflows/frozen.yml` and `.github/workflows/ddl.yml`, 9 November
2026.

## Pinned by hash

| What | Pinned to | Release | Why that one |
|---|---|---|---|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` | v7.0.1 | latest; v7 only refuses fork checkouts in `pull_request_target`, which these workflows do not use |
| `actions/setup-python` | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` | v7.1.0 | latest; v7 removed the `pip-install` input, which these workflows do not use |
| `actions/upload-artifact` | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` | v7.0.2 | latest |
| `actions/download-artifact` | `9000827ccba6bdab643e8b6fd33ac0654aef8333` | v8.0.2 | latest; v8 fails on a hash mismatch (wanted) and v5 changed paths only for downloads by ID (not used). v4 and later read each other's artifacts |
| PostgreSQL image | `postgres:18.6@sha256:e3d24f69…` | 18.6 | newest release; examples and conformance passed against it here in podman |
| MariaDB image | `mariadb:12.3.3@sha256:d46e102f…` | 12.3.3 | newest long-term-support release (to 2029-06-12). 13.0 is a rolling release with no long support, so not chosen; same checks passed |
| PyInstaller and its dependencies | `tools/freeze-requirements.txt` with `--require-hashes` | PyInstaller 6.22.3 | latest; the file lists every file PyPI has for each version, so one file serves all three platforms. Written by `tools/pin_freeze.py` |

Each `uses:` line carries its release as a comment
(`@3d3c42e… # v7.0.1`), so a reader and Dependabot both see the version. An
image is written `tag@digest`: the digest decides what is pulled, the tag is
for the reader. The four action releases all run on Node.js 24, which
removes the deprecation warning the previous versions caused.

## Not pinnable by hash, and what was done instead

- **Runner images** (`runs-on`). GitHub names them by label only and updates
  each image weekly, so no label fixes the software on it. Each is now an
  explicit version rather than `-latest`, so a new OS arrives only by a change
  here:
  - `ubuntu-22.04` for the Linux frozen build: deliberately the oldest
    supported Ubuntu, not the latest, because a frozen binary needs a glibc at
    least as new as the one it was built against. Building on 26.04 would stop
    it running on 22.04 and 24.04.
  - `windows-2025` and `macos-26` (arm64): the latest, and what `-latest`
    pointed at when the frozen build was first verified (run 42695925674).
  - `ubuntu-26.04` for the database checks and the release job: the latest.
- **Packages from apt** (`xvfb`, `postgresql-client`, `mariadb-client`). Ubuntu's
  archive keeps only the current version of each package, so a pinned version
  stops installing as soon as it is updated. They are installed by name; apt
  checks each package's signature against Ubuntu's keys, which guards their
  origin though not their version.
- **The Python interpreter** from `setup-python`. It is chosen by version
  (`3.12`, the lowest supported, so the floor is what is tested and shipped),
  and setup-python takes it from GitHub's own manifest; there is no hash
  input. Moving the frozen build to 3.14 is possible (it is what this machine
  freezes with) but is a decision about what ships, not about pinning.
- **pip itself**, which comes with that Python.

## Keeping it current

Pinned versions do not update themselves, so "latest workable" needs a
refresh now and then: `python3 tools/pin_freeze.py` for PyInstaller; for
actions and images, the commands used here were

    gh api repos/actions/checkout/releases/latest --jq .tag_name
    gh api repos/actions/checkout/commits/<tag> --jq .sha
    curl -s https://hub.docker.com/v2/repositories/library/postgres/tags/<tag>

A new database version should pass `make conformance` in podman before it is
pinned, as these did. Dependabot (`.github/dependabot.yml` with the
`github-actions` ecosystem) could propose the action updates, hashes
included; it is not set up.
