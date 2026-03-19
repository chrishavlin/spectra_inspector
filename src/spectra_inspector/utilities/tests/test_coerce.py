from spectra_inspector.utilities.coerce import (
    placeholder_to_spaces,
    spaces_to_placeholder,
)


def test_spaces_placeholder_roundtrip():
    input_str = " this is a string    with        spaces!"
    assert input_str == placeholder_to_spaces(spaces_to_placeholder(input_str))
