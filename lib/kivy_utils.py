"""Helpers for safely removing dynamically generated Kivy widgets."""

from kivy.lang import Builder


def unbind_widget_tree(widget):
    """Remove KV-created bindings for a widget and all of its children."""
    for child in list(getattr(widget, 'children', ())):
        unbind_widget_tree(child)
    Builder.unbind_widget(widget.uid)


def unbind_children(container):
    """Remove KV bindings below a container before ``clear_widgets``."""
    for child in list(getattr(container, 'children', ())):
        unbind_widget_tree(child)
