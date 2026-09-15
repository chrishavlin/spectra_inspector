"""The export fixtures of ``test_export_summary`` (the inspector module with
its conversions and metadata fetch stubbed, a spectrum figure and its
metadata) are shared with the other export tests from here."""

from spectra_inspector.tests.test_export_summary import (  # noqa: F401
    inspector,
    spectrum_figure,
    spectrum_metadata,
)
