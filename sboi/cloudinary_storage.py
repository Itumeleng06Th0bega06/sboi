"""Deterministic Cloudinary storage backend for media files.

Stores every file under its exact public_id (folder + filename), so URLs
built from stored names always match the uploaded resources.
"""
import os

import requests
import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import Storage

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.svg', '.ico'}


class CloudinaryMediaStorage(Storage):
    def _get_resource_type(self, name):
        ext = os.path.splitext(name)[1].lower()
        return 'image' if ext in IMAGE_EXTENSIONS else 'raw'

    def _public_id(self, name):
        """Cloudinary stores image public_ids without the format extension."""
        name = name.replace('\\', '/')
        if self._get_resource_type(name) == 'image':
            return os.path.splitext(name)[0]
        return name

    def _save(self, name, content):
        name = name.replace('\\', '/')
        resource_type = self._get_resource_type(name)
        cloudinary.uploader.upload(
            content,
            public_id=self._public_id(name),
            resource_type=resource_type,
            overwrite=True,
            invalidate=True,
            unique_filename=False,
        )
        return name

    def _open(self, name, mode='rb'):
        response = requests.get(self.url(name))
        if response.status_code != 200:
            raise SuspiciousFileOperation(f'File {name!r} not found in Cloudinary.')
        file = ContentFile(response.content)
        file.name = name
        return file

    def delete(self, name):
        cloudinary.uploader.destroy(
            self._public_id(name),
            resource_type=self._get_resource_type(name),
            invalidate=True,
        )

    def exists(self, name):
        try:
            cloudinary.api.resource(
                self._public_id(name),
                resource_type=self._get_resource_type(name),
            )
            return True
        except cloudinary.exceptions.NotFound:
            return False

    def size(self, name):
        try:
            return cloudinary.api.resource(
                self._public_id(name),
                resource_type=self._get_resource_type(name),
            )['bytes']
        except cloudinary.exceptions.NotFound:
            return 0

    def url(self, name):
        name = name.replace('\\', '/')
        url, _ = cloudinary.utils.cloudinary_url(
            name,
            resource_type=self._get_resource_type(name),
            secure=True,
        )
        return url