class ConsumeStalePublicMessages:
    """Drop Django messages left over from earlier requests (e.g. admin
    feedback) on public pages, without touching messages added during the
    current request. Runs before MessageMiddleware so the stale messages are
    flushed from the session/cookie storage."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/admin/'):
            return response
        storage = getattr(request, '_messages', None)
        if storage is None or getattr(storage, 'used', False):
            return response
        try:
            loaded = storage._loaded_messages
        except Exception:
            return response
        if loaded and not getattr(storage, '_queued_messages', None):
            storage.used = True
        return response