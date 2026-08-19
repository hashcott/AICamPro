# Security policy

## Supported versions

AICamPro is pre-1.0. Only the latest commit on the default branch receives
fixes.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting
(**Security → Report a vulnerability**) or email duchanhstyle@gmail.com.

Include what you found, how to reproduce it, and what an attacker could do
with it. Expect a first reply within a week.

## Scope

AICamPro runs locally and makes no network requests at runtime. The parts worth
attention are the ones that touch the system:

- `scripts/setup_v4l2loopback.sh` runs as root, writes to `/etc/modprobe.d/`
  and reloads a kernel module.
- The V4L2 layer issues raw `ioctl` calls against `/dev/video*`.
- `scripts/download_models.sh` downloads model weights over HTTPS from GitHub
  releases.

Reports about the model weights themselves belong upstream, with the projects
listed in `NOTICE`.
