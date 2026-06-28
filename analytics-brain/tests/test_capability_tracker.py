from app.services.capability_tracker import slugify_capability, PROPOSE_THRESHOLD


def test_slugify_collides_repeats():
    assert slugify_capability("Testimonials Section") == "testimonials-section"
    assert slugify_capability("testimonials_section!!") == "testimonials-section"
    assert slugify_capability("") == "unknown-capability"


def test_threshold_is_two():
    # First ask = open; second identical ask = proposed.
    assert PROPOSE_THRESHOLD == 2
