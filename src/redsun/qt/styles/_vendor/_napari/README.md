# napari's stylesheet and icons

The files in `styles/` and `icons/` are copied unchanged from napari 0.9.2
(<https://pypi.org/project/napari/0.9.2/>). They are under napari's licence,
which is in `LICENSE` in this folder.

`theme.py` and `icons.py` are written for `redsun` but follow napari's own
code, so they carry the same licence. They fill the stylesheets' placeholders
from a theme and write the icons in its colours.

`redsun` keeps this copy until napari publishes its styling as a package of
its own. This folder is then replaced by a dependency on that package.
