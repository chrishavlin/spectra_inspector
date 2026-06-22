from abc import ABC


class indexedLayoutIDMapper(ABC):
    id_type_base: str
    index: int | None
    prop_names: tuple[str, ...] = ("div",)

    def __init__(self, id_type_base: str, index: int | None = None) -> None:
        self.id_type_base = id_type_base
        self.index = index

    @property
    def div(self) -> str:
        return self.full_id("-div")

    def full_id(self, id_suffix: str) -> str:
        return self.id_type_base + id_suffix

    def get_id_with_index(self, prop: str) -> dict[str, str | int]:
        full_id: dict[str, str | int] = {"type": str(getattr(self, prop))}
        if self.index is not None:
            full_id["index"] = self.index
        return full_id
