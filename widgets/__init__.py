"""
Widget package for the fire dashboard.

Each teammate owns one module in this package and exposes a single
`create_panel()` function that returns a Panel component. The base app
(`app.py`) imports each module and lays the widgets out in a grid.

Keeping one widget per file means four people can work in parallel without
stepping on each other or causing merge conflicts in the base app.
"""
