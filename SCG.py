"""Public SCG entry point; FCCG.py remains a compatible legacy launcher."""
from tools.launch import Application_Start

if __name__ == "__main__":
    raise SystemExit(Application_Start("SCG"))
