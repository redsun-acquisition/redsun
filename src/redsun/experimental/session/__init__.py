"""Container and component definitions for the experimental layer.

Re-exports live in `redsun.experimental`: `session` and `virtual` depend on
each other here - the dependency resolution in `session` is what
`virtual._shared` asks for a census with - so a re-export in either package
closes an import cycle.
"""
