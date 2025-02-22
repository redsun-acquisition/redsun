# type: ignore
# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
from importlib.metadata import version as get_version
from pathlib import Path

sys.path.insert(0, str(Path('..', 'src').resolve()))

project = 'Redsun'
copyright = '2024, Jacopo Abramo'
author = 'Jacopo Abramo'

version = get_version("redsun").split(".dev")[0]
github_user = "redsun-acquisition"
github_repo = "redsun"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.githubpages',
    'sphinx_design',
    'myst_parser',
]

myst_enable_extensions = ['attrs_block', 'colon_fence']

exclude_patterns = ['_build']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'pydata_sphinx_theme'
html_static_path = ["_static"]
html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": f"https://github.com/{github_user}/{github_repo}",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        }
   ],
    "switcher": {
        "json_url": "https://redsun-acquisition.github.io/redsun/main/_static/switcher.json",
        "version_match": version,
    },
    "navbar_start": ["navbar-logo", "version-switcher"],
}

html_context = {
    # this doesn't really matter;
    # adding it only for completion
    "default_mode": "auto",
}

source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

napoleon_google_docstring = False
napoleon_numpy_docstring = True
autodoc_typehints = 'description'
