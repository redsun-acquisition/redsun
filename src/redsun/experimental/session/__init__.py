"""Container and component definitions for the experimental layer.

Re-exports live in `redsun.experimental`: `containers` and `virtual` depend on
each other here - the dependency resolution in `containers` is what
`virtual._container` asks for a census with - so a re-export in either package
closes an import cycle.
"""
