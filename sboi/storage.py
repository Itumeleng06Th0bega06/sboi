from whitenoise.storage import CompressedManifestStaticFilesStorage


class NonStrictManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest static storage that tolerates missing manifest entries.

    Jazzmin's base template requests a bare directory path
    ({% static 'vendor/bootswatch' %}) which can never exist in the
    manifest; strict mode raises ValueError and 500s every admin page.
    Missing entries fall back to their plain unhashed URL instead.
    Real files are still hashed and cache-busted as normal.
    """

    manifest_strict = False
