_place_holder = "___"


def spaces_to_placeholder(input: str) -> str:
    return input.replace(" ", _place_holder)


def placeholder_to_spaces(input: str) -> str:
    return input.replace(_place_holder, " ")
