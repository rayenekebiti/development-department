_HANDLERS = {}


def on(event):
    def register(fn):
        _HANDLERS.setdefault(event, []).append(fn)
        return fn
    return register


def emit(event, payload):
    for fn in _HANDLERS.get(event, []):
        fn(payload)
