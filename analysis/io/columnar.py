from pathlib import Path

import awkward as ak



def read_parquet(path: Path) -> ak.Array:
    return ak.from_parquet(path)



def write_parquet(events: ak.Array, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ak.to_parquet(events, path)
