# Contributing

Thanks for taking a look.

This project is strict about one thing: speed work does not count if it weakens
Tor privacy, browser safety, or compatibility.

## Before you propose a change

- Do not suggest shortcuts that weaken Tor path rules, fingerprint protections,
  or DNS safety.
- Keep benchmark claims tied to saved evidence.
- Prefer small, reviewable patches.

## Quick local checks

Run these before opening a pull request:

```sh
python3 -m py_compile $(find torfast tools tests -name '*.py' | sort)
python3 -m unittest \
  tests.test_path_rules \
  tests.test_browser_defaults \
  tests.test_browser_install \
  tests.test_torfast_main
```

## For larger speed claims

- Explain the privacy risk you considered.
- Point to the saved benchmark or quality evidence.
- Say whether the change is safe by default or still lab-only.
