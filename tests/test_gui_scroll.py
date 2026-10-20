from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.gui import ScrollableFrame


class FakeWidget:
    def __init__(self, master=None):
        self.master = master


class FakeCanvas:
    def __init__(self):
        self.scrolls = []

    def yview_scroll(self, units, what):
        self.scrolls.append((units, what))


class ScrollFrameHarness:
    _event_inside = ScrollableFrame._event_inside
    _wheel = ScrollableFrame._wheel
    _wheel_global = ScrollableFrame._wheel_global

    def __init__(self, mapped=True):
        self.body = FakeWidget()
        self.canvas = FakeCanvas()
        self.scrollbar = FakeWidget()
        self.mapped = mapped

    def winfo_ismapped(self):
        return self.mapped


class ScrollableFrameTests(unittest.TestCase):
    def test_mouse_wheel_scrolls_only_when_originated_inside_this_frame(self):
        frame = ScrollFrameHarness()
        event = SimpleNamespace(widget=FakeWidget(frame.body), delta=-120)

        self.assertEqual(frame._wheel(event), "break")
        self.assertEqual(frame.canvas.scrolls, [(1, "units")])

    def test_mouse_wheel_ignores_other_frames_and_unmapped_tabs(self):
        frame = ScrollFrameHarness()
        unrelated = FakeWidget(FakeWidget())
        self.assertIsNone(frame._wheel(SimpleNamespace(widget=unrelated, delta=-120)))
        self.assertEqual(frame.canvas.scrolls, [])

        hidden = ScrollFrameHarness(mapped=False)
        self.assertIsNone(hidden._wheel(SimpleNamespace(widget=FakeWidget(hidden.body), delta=120)))
        self.assertEqual(hidden.canvas.scrolls, [])

    def test_linux_wheel_buttons_are_scoped_to_the_owning_frame(self):
        frame = ScrollFrameHarness()
        event = SimpleNamespace(widget=FakeWidget(frame.body), num=4)
        self.assertEqual(frame._wheel_global(event), "break")
        self.assertEqual(frame.canvas.scrolls, [(-1, "units")])

        event_other_frame = SimpleNamespace(widget=FakeWidget(), num=5)
        self.assertIsNone(frame._wheel_global(event_other_frame))
        self.assertEqual(frame.canvas.scrolls, [(-1, "units")])

    def test_scrollbar_is_an_owned_scroll_target(self):
        frame = ScrollFrameHarness()
        event = SimpleNamespace(widget=frame.scrollbar, delta=120)
        self.assertEqual(frame._wheel(event), "break")
        self.assertEqual(frame.canvas.scrolls, [(-1, "units")])


if __name__ == "__main__":
    unittest.main()
