from pathlib import Path


def test_project_structure_exists():
    root = Path(__file__).resolve().parents[1]
    expected = [
        "src/green_direct/io",
        "src/green_direct/models",
        "src/green_direct/core",
        "src/green_direct/batch",
        "src/green_direct/export",
        "src/green_direct/economy",
        "src/green_direct/ui",
        "outputs",
    ]
    for path in expected:
        assert (root / path).exists()
