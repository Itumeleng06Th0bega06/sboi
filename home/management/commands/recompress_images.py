"""Recompress already-stored media images in place.

Runs every stored image through the same pipeline used for uploads
(sboi.image_utils.optimize_image) and replaces the stored file under its
exact current name, so URLs and database references stay valid.
"""
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from sboi.fields import OptimizedImageField
from sboi.image_utils import optimize_image


class Command(BaseCommand):
    help = (
        'Recompress stored images with the upload pipeline. '
        'Dry-run by default; pass --apply to write changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually replace files in storage (default: report only).',
        )
        parser.add_argument(
            '--min-saving', type=int, default=10, dest='min_saving',
            help='Minimum percent size reduction required to replace a file (default: 10).',
        )
        parser.add_argument(
            '--media-root', dest='media_root',
            help='Operate on a local folder instead of the configured storage (testing).',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        min_ratio = 1 - options['min_saving'] / 100.0
        storage = default_storage
        if options['media_root']:
            from django.core.files.storage.filesystem import FileSystemStorage
            storage = FileSystemStorage(
                location=options['media_root'], allow_overwrite=True,
            )

        fields = [
            (model, field)
            for model in apps.get_models()
            for field in model._meta.get_fields()
            if isinstance(field, OptimizedImageField)
        ]
        if not fields:
            self.stdout.write(self.style.WARNING('No OptimizedImageField models found.'))
            return

        names = set()
        for model, field in fields:
            values = (
                model.objects.exclude(**{field.name: ''})
                .values_list(field.name, flat=True)
            )
            names.update(v.replace('\\', '/') for v in values if v)

        self.stdout.write(f'{len(names)} unique image(s) across {len(fields)} field(s).\n')

        total_before = total_after = replaced = kept = skipped = failed = 0
        for name in sorted(names):
            try:
                old_size = storage.size(name)
                with storage.open(name, 'rb') as fh:
                    raw = fh.read()
                result = optimize_image(raw, name)
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'ERROR   {name}: {exc}'))
                continue

            if not result:
                skipped += 1
                self.stdout.write(f'SKIP    {name}: not recompressible (SVG/corrupt/animated)')
                continue

            data, _ = result
            new_size = len(data)
            total_before += old_size
            total_after += min(new_size, old_size)

            if old_size and new_size < old_size * min_ratio:
                saved_pct = round(100 * (old_size - new_size) / old_size)
                if apply_changes:
                    try:
                        # _save writes at exactly `name`; public save() would rename.
                        # Cloudinary backend uploads with overwrite+invalidate;
                        # FileSystemStorage overwrites the local file directly.
                        storage._save(name, ContentFile(data))
                    except Exception as exc:
                        failed += 1
                        self.stderr.write(self.style.ERROR(f'ERROR   {name}: {exc}'))
                        continue
                    replaced += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'REPLACED {name}: {self._kb(old_size)} -> {self._kb(new_size)} (-{saved_pct}%)'
                    ))
                else:
                    replaced += 1
                    self.stdout.write(
                        f'WOULD REPLACE {name}: {self._kb(old_size)} -> {self._kb(new_size)} (-{saved_pct}%)'
                    )
            else:
                kept += 1
                self.stdout.write(f'KEPT    {name}: {self._kb(old_size)} (already optimal)')

        self.stdout.write('')
        if apply_changes:
            summary = f'Done. Replaced: {replaced}, kept: {kept}, skipped: {skipped}, errors: {failed}.'
        else:
            summary = (
                f'Dry run — nothing written. Replaceable: {replaced}, '
                f'kept: {kept}, skipped: {skipped}, errors: {failed}. '
                f'Re-run with --apply to write.'
            )
        if total_before:
            summary += (
                f'\nStorage: {self._kb(total_before)} -> {self._kb(total_after)} '
                f'({round(100 * (total_before - total_after) / total_before)}% smaller)'
            )
        self.stdout.write(self.style.MIGRATE_HEADING(summary))

    @staticmethod
    def _kb(size):
        return f'{size / 1024:.0f} KB'
