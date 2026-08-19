# Contributing to AICamPro

Thanks for taking a look. This is a small project with a specific target —
Linux, an AMD GPU, ROCm — so the most useful contributions are usually the ones
that come with a note about the hardware you tested on.

## Getting set up

```bash
git clone https://github.com/hashcott/AICamPro.git
cd AICamPro
./scripts/setup_env.sh          # conda env + PyTorch ROCm
./scripts/download_models.sh    # matting + face detection models
./run.sh --check                # confirms GPU, models and devices
```

`--check` is the fastest way to tell whether a problem is your setup or the
code. If it reports a CPU device, ROCm is not reaching the GPU and nothing else
will make sense.

## Before you open a pull request

```bash
ruff check aicampro tests
python -m pytest
```

`ruff` is pinned to the version CI uses (see `[project.optional-dependencies]`)
because its default rule set changes between releases. The rule selection lives
in `pyproject.toml`, not in CI, so both agree.

Most of the suite needs a GPU and skips itself without one. That means a green
run on a machine with no AMD card proves much less than you might think — say
in the PR which of the two you ran.

## Two rules that are easy to miss

**Adding a field to `AppConfig` means adding a line to `CASES` in
`tests/test_config_wiring.py`.** That test exists because a setting was once
wired to nothing at all: the UI wrote `background.image_path`, the pipeline
never read it, and the compositor quietly fell back to a solid colour. No error,
no warning, the feature simply did nothing. The test runs a frame through the
real pipeline and asserts every setting leaves a trace on the output.

**User-visible strings are Vietnamese.** The UI, the log messages and the code
comments are in Vietnamese; identifiers, commit messages and the documents in
this repository's root are in English. `README.vi.md` is the Vietnamese README.

## Commit messages

Written in English, in the imperative, with a body that explains *why*. The
"what" is already in the diff. Traps and measurements are especially worth
recording — several commits here carry numbers like "BUFFERSIZE=1 halves the
frame rate" precisely so nobody has to rediscover them.

No `Co-Authored-By` trailers.

## Where things live

| Path | What it holds |
| --- | --- |
| `aicampro/core/` | capture, V4L2, pipeline, virtual camera, recording |
| `aicampro/gpu/` | everything that runs on the GPU — tensors are `(1, 3, H, W)`, RGB, 0..1 |
| `aicampro/vision/` | auto-framing |
| `aicampro/ui/` | PySide6 widgets and the main window |
| `scripts/` | environment, model download, v4l2loopback setup |
| `CLAUDE.md` | architecture notes and the list of traps already paid for (Vietnamese) |

Read `CLAUDE.md` before touching the pipeline or the Qt stylesheet. It is a
list of things that cost real debugging time — a `QWidget { background: … }`
rule that silently breaks every slider, a `QComboBox.findData` that compares
tuples by identity, a `CAP_PROP_BUFFERSIZE` that halves the frame rate.

## Cutting a release

Releases are made by pushing a tag; nothing is uploaded by hand.

1. Bump `version` in `pyproject.toml`.
2. Move the `Unreleased` entries in `CHANGELOG.md` under the new version with
   today's date, and add the two link definitions at the bottom.
3. Commit, then tag and push:
   ```bash
   git tag -a v0.2.0 -m "AICamPro v0.2.0"
   git push origin main --tags
   ```

`.github/workflows/release.yml` then lints, tests, checks that the tag matches
the version in `pyproject.toml`, builds an sdist and a wheel, pulls the release
notes out of `CHANGELOG.md`, and publishes the GitHub release with both
artifacts attached. A mismatched tag fails the job rather than shipping.

## Reporting bugs

Include the output of `./run.sh --check`, your distribution and kernel, and the
ROCm/PyTorch versions. The issue template asks for exactly these.
