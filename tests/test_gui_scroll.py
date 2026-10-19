"""Regression tests for routing global Tk mouse-wheel events."""

from types import SimpleNamespace
import unittest

from app.gui import ScrollableFrame


class FakeWidget:
    def __init__(self, master=None):
        self.master = master
        self.scrolls = []

    def yview_scroll(self, units, _what):
        self.scrolls.append(units)


class ScrollableFrameWheelTests(unittest.TestCase):
    def make_frame(self):
        canvas = FakeWidget()
        body = FakeWidget(master=canvas)
        scrollbar = FakeWidget()
        frame = SimpleNamespace(body=body, canvas=canvas, scrollbar=scrollbar)
        frame._event_belongs_to_frame = (
            lambda event: ScrollableFrame._event_belongs_to_frame(frame, event)
        )
        return frame

    def test_only_frame_under_pointer_scrolls(self):
        active = self.make_frame()
        inactive = self.make_frame()
        child = FakeWidget(master=FakeWidget(master=active.body))
        event = SimpleNamespace(widget=child, delta=120)

        self.assertEqual(ScrollableFrame._wheel(active, event), "break")
        self.assertIsNone(ScrollableFrame._wheel(inactive, event))
        self.assertEqual(active.canvas.scrolls, [-1])
        self.assertEqual(inactive.canvas.scrolls, [])

    def test_small_nonzero_trackpad_delta_scrolls_one_unit(self):
        frame = self.make_frame()
        event = SimpleNamespace(widget=frame.body, delta=30)

        self.assertEqual(ScrollableFrame._wheel(frame, event), "break")
        self.assertEqual(frame.canvas.scrolls, [-1])

    def test_linux_wheel_buttons_are_routed_to_matching_frame(self):
        active = self.make_frame()
        inactive = self.make_frame()
        child = FakeWidget(master=active.body)

        self.assertEqual(
            ScrollableFrame._wheel_linux(active, SimpleNamespace(widget=child, num=4)),
            "break",
        )
        self.assertIsNone(
            ScrollableFrame._wheel_linux(inactive, SimpleNamespace(widget=child, num=5))
        )
        self.assertEqual(active.canvas.scrolls, [-1])
        self.assertEqual(inactive.canvas.scrolls, [])

        self.assertEqual(
            ScrollableFrame._wheel_linux(active, SimpleNamespace(widget=child, num=5)),
            "break",
        )
        self.assertEqual(active.canvas.scrolls, [-1, 1])

    def test_scrollbar_itself_is_considered_part_of_the_frame(self):
        frame = self.make_frame()
        event = SimpleNamespace(widget=frame.scrollbar, delta=-120)

        self.assertEqual(ScrollableFrame._wheel(frame, event), "break")
        self.assertEqual(frame.canvas.scrolls, [1])

    def test_events_from_unrelated_widgets_are_ignored(self):
        frame = self.make_frame()
        event = SimpleNamespace(widget=FakeWidget(), delta=120)

        self.assertIsNone(ScrollableFrame._wheel(frame, event))
        self.assertIsNone(
            ScrollableFrame._wheel_linux(frame, SimpleNamespace(widget=event.widget, num=4))
        )
        self.assertEqual(frame.canvas.scrolls, [])


if __name__ == "__main__":
    unittest.main()
