# Security Policy

This project touches Tor Browser launch paths, proxy behavior, benchmark
automation, and privacy-sensitive defaults.

If you find a security issue, privacy regression, or anything that could weaken
Tor-style protections:

- please do not open a public issue first
- report enough detail to reproduce the problem
- include affected files, commands, and any saved proof you used

For non-sensitive bugs, normal GitHub issues are fine.

## Scope notes

- Performance wins do not count if they weaken privacy or compatibility.
- Lab-only switches should stay clearly separated from safe-by-default paths.
- Browser fingerprinting, DNS behavior, and path safety are high-sensitivity
  areas for this repo.
