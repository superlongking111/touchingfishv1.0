from fishmate.ui.widgets.toast_fade import (
    DEFAULT_TOAST_DISPLAY_SEC,
    DEFAULT_TOAST_FADE_OUT_SEC,
    toast_fade_out_ms,
    toast_hold_ms,
)


def test_toast_timing_ten_plus_four():
    assert toast_hold_ms(10, DEFAULT_TOAST_FADE_OUT_SEC) == 6000
    assert toast_fade_out_ms(DEFAULT_TOAST_FADE_OUT_SEC) == 4000
    assert DEFAULT_TOAST_DISPLAY_SEC == 10
