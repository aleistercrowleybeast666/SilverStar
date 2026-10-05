"""Public generator exports, loaded on demand to avoid import cycles."""

from importlib import import_module

__all__ = [
    "ApplyResult",
    "GenerationPlan",
    "ProjectAssembler",
    "SourceGraph",
    "SourceGraph_Resolve",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    module = "source_graph" if name in {"SourceGraph", "SourceGraph_Resolve"} else "assembler"
    return getattr(import_module(f"silverstar_fccg.generator.{module}"), name)
