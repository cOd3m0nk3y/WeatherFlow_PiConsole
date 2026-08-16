import unittest
from unittest.mock import patch

from lib.kivy_utils import unbind_children, unbind_widget_tree


class FakeWidget:
    def __init__(self, uid, children=None):
        self.uid = uid
        self.children = children or []


class KivyUtilsTests(unittest.TestCase):
    @patch('lib.kivy_utils.Builder.unbind_widget')
    def test_unbinds_descendants_before_parent(self, unbind):
        tree = FakeWidget(1, [FakeWidget(2, [FakeWidget(3)])])
        unbind_widget_tree(tree)
        self.assertEqual([call.args[0] for call in unbind.call_args_list],
                         [3, 2, 1])

    @patch('lib.kivy_utils.Builder.unbind_widget')
    def test_unbinds_container_children_without_container(self, unbind):
        container = FakeWidget(1, [FakeWidget(2), FakeWidget(3)])
        unbind_children(container)
        self.assertEqual([call.args[0] for call in unbind.call_args_list],
                         [2, 3])


if __name__ == '__main__':
    unittest.main()
