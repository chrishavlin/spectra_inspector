"""The sample name's trip through the inspector's URL.

The inspector is registered on ``/inspector/<sample_name>`` and Dash hands
``layout()`` the browser's ``window.location.pathname`` segment verbatim: it
percent-decodes query strings but not path variables. So the data selection
page encodes the name once when it builds the link and the inspector decodes
it once on entry, and nothing in between sees anything but the real name.

Sample names are paths relative to the data root (``/dir/sub dir/map.spd``);
their slashes are kept so the URL stays readable.
"""

from urllib.parse import quote, unquote


def sample_name_to_url(sample_name: str) -> str:
    return quote(sample_name, safe="/")


def url_to_sample_name(url_segment: str) -> str:
    return unquote(url_segment)
