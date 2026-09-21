"""PyInstaller entry point.

se7e/app.py can't be PyInstaller's entry script directly: it uses relative
imports ("from . import autostart"), which only work when the module is
imported as part of its package, not when frozen as the top-level __main__
script. This thin wrapper does a real package import instead.
"""
from se7e.app import main

if __name__ == "__main__":
    main()
