from hydra.primitives.registry import build_primitives


class Executor:
    def __init__(self):
        self._primitives = build_primitives()

    def get(self, primitive_id: str):
        try:
            return self._primitives[primitive_id]
        except KeyError as exc:
            raise KeyError(f"unknown primitive {primitive_id}") from exc
