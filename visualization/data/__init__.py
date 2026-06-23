"""Data-access layer: the DataSource seam and its concrete implementations.

View code (map, timeline, HUD) depends only on `source.DataSource` and the
frozen value objects in `models`. CSV/pandas specifics live in `csv_source`.
"""
