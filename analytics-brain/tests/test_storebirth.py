from app.routers.brand import sse_event, STOREBIRTH_STEPS


def test_sse_event_frame_format():
    frame = sse_event("step", {"step": "analyzing_logo", "index": 0})
    assert frame.startswith("event: step\n")
    assert 'data: {"step": "analyzing_logo"' in frame
    assert frame.endswith("\n\n")


def test_steps_cover_full_pipeline_with_model_labels():
    steps = dict(STOREBIRTH_STEPS)
    assert "analyzing_logo" in steps and "composing_layout" in steps
    # qwen-vl-max and qwen-max are both visibly labeled (judges see the chain).
    labels = " ".join(steps.values())
    assert "qwen-vl-max" in labels and "qwen-max" in labels
