# validate-mo

Checks the `.mo` files changed in a pull request. `.mo` files are binary and cannot be reviewed in a diff.

- **Fails the job** when a `.mo` is not a strictly well-formed catalog (bad header, offsets out of range, UTF-8 errors, unreferenced or trailing bytes), a symlink, or executable. Other changed files are ignored.
- **Warns** (annotation on the file) when a `.mo` differs from its sibling `.po` compiled with `msgfmt`, with counts and a sample of differing msgids, or when no sibling `.po` exists.

```yaml
on: pull_request
jobs:
  validate-mo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: scarf005/validate-mo@v1
```

A `.mo` is compared with the `.po` of the same name next to it, or `lang/po/<loc>.po` for `lang/mo/<loc>/LC_MESSAGES/*.mo`. Requires `pull-requests: read`. Installs `gettext` (`msgfmt`) with apt when missing, so use a Debian-based runner.
Inputs: `token`.
