## What this changes

<!-- One or two sentences. The "why" matters more than the "what". -->

## How it was verified

<!--
Say what you actually ran, not what should work. For anything touching the GPU
pipeline, a before/after frame is worth more than a description.
-->

- [ ] `python -m pytest`
- [ ] `ruff check aicampro tests`
- [ ] Ran the app and exercised the change

## Notes for the reviewer

<!-- Trade-offs, things you are unsure about, follow-up work. -->

---

- [ ] If this adds a field to `AppConfig`, I added a line to `CASES` in
      `tests/test_config_wiring.py` so the setting is proven to affect output.
- [ ] User-visible strings are in Vietnamese, matching the rest of the UI.
