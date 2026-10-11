# validate-mo

Checks the `.mo` files changed in a pull request. `.mo` files are binary and cannot be reviewed in a diff.

- **Fails the job** when a `.mo` is not a strictly well-formed catalog (bad header, offsets out of range, UTF-8 errors, unreferenced or trailing bytes), or when the PR changes a file that does not match `pattern`, a symlink, or an executable.
- **Warns** (annotation on the file) when a `.mo` differs from its sibling `.po` compiled with `msgfmt`, with counts and a sample of differing msgids, or when no sibling `.po` exists.

```yaml
on: pull_request
jobs:
  validate-mo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarf005/validate-mo@v1
```

Requires `msgfmt` (preinstalled on `ubuntu-latest`) and `pull-requests: read`.
Inputs: `pattern` (regex all changed files must match; default `(?:.*/)?lang/[^/]+\.(?:po|mo|pot)`), `token`.
