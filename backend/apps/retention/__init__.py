"""Data retention (T-073, DATA-12): how long each class of data is kept, who approved that, and
the job that applies it.

May import: apps.imports (services), apps.audit (services); plus apps.api. A class is only ever
reduced when it has a period AND an approval, so with no policy the job does nothing (D-015).
"""
