"""Project checks — the functions whose text goes into the prompt.

Write one per file, register it with `@check("<ad>")`, then import that module
here so the registration runs. The name is what the profile lists under
`checks` and what the template writes as `$<ad>`.
"""

from app.checks import ornek  # noqa: F401  (içe alınmazsa @check koşmaz, kayıt olmaz)
