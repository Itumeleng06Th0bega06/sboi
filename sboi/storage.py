from whitenoise.storage import CompressedManifestStaticFilesStorage


class NonStrictManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest static storage that tolerates missing manifest entries.

    Templates sometimes request a bare directory path (for example a vendor
    asset folder) which can never exist as a manifest entry. Strict mode
    raises ValueError and 500s the page that references it. Missing entries
    fall back to their plain unhashed URL instead. Real files are still
    hashed and cache-busted as normal.
    """

    manifest_strict = False
