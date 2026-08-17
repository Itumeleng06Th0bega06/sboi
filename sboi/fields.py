import io

from django.db.models.fields.files import ImageField

from .image_utils import optimize_image


class OptimizedImageField(ImageField):
    """ImageField that downscales and recompresses uploads before storage."""

    def pre_save(self, model_instance, add):
        file = getattr(model_instance, self.attname)
        if file and not getattr(file, '_committed', True) and getattr(file, 'file', None) is not None:
            try:
                raw = file.read()
            except Exception:
                raw = None
            if raw:
                result = optimize_image(raw, file.name)
                if result:
                    data, name = result
                    file.file = io.BytesIO(data)
                    file.name = name
                    file.size = len(data)
        return super().pre_save(model_instance, add)