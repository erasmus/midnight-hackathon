from core.sparkline import sparkline_svg


def points(*ratings):
    return [{"date": f"2024-01-{i + 1:02d}", "rating": r} for i, r in enumerate(ratings)]


def test_a_history_renders_an_svg():
    svg = sparkline_svg(points(2400, 2500, 2600))
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_the_svg_contains_a_polyline():
    assert "<polyline" in sparkline_svg(points(2400, 2500, 2600))


def test_every_point_becomes_a_coordinate():
    svg = sparkline_svg(points(2400, 2500, 2600, 2700))
    polyline = svg.split('points="')[1].split('"')[0]
    assert len(polyline.split()) == 4


def test_an_empty_history_renders_nothing():
    assert sparkline_svg([]) == ""


def test_a_single_point_renders_nothing():
    # One point is not a trajectory.
    assert sparkline_svg(points(2400)) == ""


def test_a_flat_history_does_not_divide_by_zero():
    svg = sparkline_svg(points(2500, 2500, 2500))
    assert "<svg" in svg and "nan" not in svg.lower()


def test_the_rating_range_is_labelled():
    svg = sparkline_svg(points(2400, 2900))
    assert "2400" in svg and "2900" in svg


def test_points_without_a_rating_are_ignored():
    history = points(2400, 2600) + [{"date": "2024-02-01"}]
    svg = sparkline_svg(history)
    polyline = svg.split('points="')[1].split('"')[0]
    assert len(polyline.split()) == 2


def test_history_is_plotted_in_date_order():
    unordered = [
        {"date": "2024-03-01", "rating": 2600},
        {"date": "2024-01-01", "rating": 2400},
    ]
    svg = sparkline_svg(unordered)
    coords = svg.split('points="')[1].split('"')[0].split()
    ys = [float(c.split(",")[1]) for c in coords]
    assert ys[0] > ys[1]  # SVG y grows downward, so a rise means y decreases


def test_the_svg_has_no_external_references():
    svg = sparkline_svg(points(2400, 2500))
    assert "http://" not in svg and "https://" not in svg


def test_dimensions_can_be_set():
    svg = sparkline_svg(points(2400, 2500), width=400, height=80)
    assert 'width="400"' in svg and 'height="80"' in svg


def test_the_svg_adapts_to_theme_via_current_color():
    assert "currentColor" in sparkline_svg(points(2400, 2500))
