from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from whitenoise.storage import CompressedManifestStaticFilesStorage


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """Storage for files that must never be served by the web server directly.

    The location lives outside ``MEDIA_ROOT``; views in the communications app
    check conversation membership before streaming a file back. The storage is
    deconstructible so Django can serialise it into migrations without baking
    an absolute path into the repository.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.PRIVATE_MEDIA_ROOT)
        kwargs['base_url'] = None
        super().__init__(*args, **kwargs)


class NonStrictManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest static storage that tolerates missing manifest entries.

    Templates sometimes request a bare directory path (for example a vendor
    asset folder) which can never exist as a manifest entry. Strict mode
    raises ValueError and 500s the page that references it. Missing entries
    fall back to their plain unhashed URL instead. Real files are still
    hashed and cache-busted as normal.
    """

    manifest_strict = False
