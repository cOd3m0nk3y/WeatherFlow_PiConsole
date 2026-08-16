"""Compact daily temperature graph panel."""

from kivy.app import App
from kivy.graphics import Color, Line
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget

from panels.template import panelTemplate


class TemperatureDayGraph(Widget):
    actual = ListProperty([])
    baseline = ListProperty([])
    current_forecast = ListProperty([])
    now_hour = NumericProperty(0)
    minimum_label = StringProperty('--')
    maximum_label = StringProperty('--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.redraw, size=self.redraw, actual=self.redraw,
                  baseline=self.redraw, current_forecast=self.redraw,
                  now_hour=self.redraw)

    def _coordinates(self, points, low, high):
        width = max(self.width, 1)
        height = max(self.height, 1)
        span = max(high - low, 1)
        coordinates = []
        for hour, temperature in points:
            coordinates.extend((self.x + max(0, min(24, hour)) / 24 * width,
                                self.y + (temperature - low) / span * height))
        return coordinates

    def redraw(self, *args):
        values = [point[1] for series in
                  (self.actual, self.baseline, self.current_forecast)
                  for point in series if len(point) == 2]
        if values:
            low = min(values)
            high = max(values)
            padding = max((high - low) * .12, 1)
            low -= padding
            high += padding
            self.minimum_label = '{:.0f}°'.format(low)
            self.maximum_label = '{:.0f}°'.format(high)
        else:
            low, high = 0, 1
            self.minimum_label = self.maximum_label = '--'

        self.canvas.clear()
        with self.canvas:
            Color(.22, .22, .22, 1)
            for hour in (0, 6, 12, 18, 24):
                x = self.x + hour / 24 * self.width
                Line(points=[x, self.y, x, self.top], width=.7)
            for fraction in (0, .5, 1):
                y = self.y + fraction * self.height
                Line(points=[self.x, y, self.right, y], width=.7)

            if len(self.baseline) > 1:
                Color(.65, .65, .65, .9)
                Line(points=self._coordinates(self.baseline, low, high),
                     width=1.15, dash_length=4, dash_offset=3)
            if len(self.actual) > 1:
                Color(0, .72, .79, 1)
                Line(points=self._coordinates(self.actual, low, high), width=1.8)
            if len(self.current_forecast) > 1:
                Color(1, .36, .25, 1)
                Line(points=self._coordinates(self.current_forecast, low, high),
                     width=1.6, dash_length=5, dash_offset=3)

            Color(1, 1, 1, .45)
            now_x = self.x + max(0, min(24, self.now_hour)) / 24 * self.width
            Line(points=[now_x, self.y, now_x, self.top], width=.8)


class DailyTemperaturePanel(panelTemplate):
    pass


class DailyTemperatureButton(RelativeLayout):
    pass
