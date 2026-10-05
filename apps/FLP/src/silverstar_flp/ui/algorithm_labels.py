"""Presentation spelling for algorithm names; persisted IDs stay unchanged."""


def AlgorithmName_Display(name: str) -> str:
    return name.replace("KF_6", "KF6").replace("ESKF_15", "ESKF15")
