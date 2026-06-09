"""Jubilee automation Python package.

Hardware coordination, motion control, job logging, and Google Drive backup
live under this package. Import submodules directly rather than from this
``__init__``.

Example:
    Typical imports::

        from src.JubileeManager import JubileeManager
        from src.JobLog import JobLog
        from src.ConfigLoader import config

Note:
    This package root does not re-export symbols. Use the submodule that owns
    the class or function you need.
"""
