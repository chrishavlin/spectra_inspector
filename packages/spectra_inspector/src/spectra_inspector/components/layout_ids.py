"""Component ids, declared once per component.

A component's ids are a class of `ID` attributes under a common base, so a
layout and the callbacks that address it name every element the same way::

    class elementDropdownSliderIDS(indexedLayoutIDMapper, base="element-slider"):
        dropdown = ID()
        apply = ID("-refreshbutton")  # an id that differs from the attribute

    ids = elementDropdownSliderIDS(index=2)
    ids.dropdown             # "element-slider-dropdown", a plain id
    ids.dropdown.indexed     # {"type": "element-slider-dropdown", "index": 2}
    ids.dropdown.at(MATCH)   # the same id type under a callback wildcard

An instance built with another base (`ids_class("other-base")`) addresses a
second copy of the component without its ids colliding with the first.
"""

from typing import Any, ClassVar, Self

IDIndex = int | str | None
PatternID = dict[str, Any]


class LayoutID(str):
    """One element's id: the plain string, which is also the ``type`` of its
    pattern-matching ids."""

    __slots__ = ("_index",)
    _index: IDIndex

    def __new__(cls, value: str, index: IDIndex = None) -> Self:
        layout_id = super().__new__(cls, value)
        layout_id._index = index
        return layout_id

    def at(self, index: Any, **keys: Any) -> PatternID:
        """The pattern-matching id at ``index`` (a value or a wildcard), with
        any further keys the component matches on."""
        return {"type": str(self), "index": index, **keys}

    @property
    def indexed(self) -> PatternID:
        """The pattern-matching id at the index its mapper was built with."""
        if self._index is None:
            return {"type": str(self)}
        return self.at(self._index)


class ID:
    """Declares one element of a component, ``<base>-<attribute name>`` unless
    a suffix is given."""

    def __init__(self, suffix: str | None = None) -> None:
        self.suffix = suffix

    def __set_name__(self, owner: type, name: str) -> None:
        if self.suffix is None:
            self.suffix = f"-{name}"

    def __get__(
        self, obj: "indexedLayoutIDMapper | None", objtype: type | None = None
    ) -> LayoutID:
        if obj is None:
            msg = "A component's ids are read from an instance of its mapper."
            raise AttributeError(msg)
        return obj.full_id(str(self.suffix))


class indexedLayoutIDMapper:
    default_base: ClassVar[str | None] = None
    # every declared `ID`, base class first
    prop_names: ClassVar[tuple[str, ...]] = ("div",)

    div = ID()

    def __init_subclass__(cls, base: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if base is not None:
            cls.default_base = base
        names: dict[str, None] = {}
        for klass in reversed(cls.__mro__):
            names.update({k: None for k, v in vars(klass).items() if isinstance(v, ID)})
        cls.prop_names = tuple(names)

    def __init__(self, id_type_base: str | None = None, index: IDIndex = None) -> None:
        base = self.default_base if id_type_base is None else id_type_base
        if base is None:
            msg = f"{type(self).__name__} has no default base, pass id_type_base."
            raise TypeError(msg)
        self.id_type_base = base
        self.index = index

    def full_id(self, id_suffix: str) -> LayoutID:
        return LayoutID(self.id_type_base + id_suffix, self.index)
