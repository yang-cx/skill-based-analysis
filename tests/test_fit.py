from analysis.stats.fit import build_parser


def test_fit_parser():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--workspace",
            "w.json",
            "--fit-id",
            "FIT1",
            "--out",
            "o.json",
        ]
    )
    assert args.fit_id == "FIT1"
    assert args.backend == "pyhf"

