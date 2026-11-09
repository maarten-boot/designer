"""What PyInstaller freezes: a script outside any package, so it imports the
real entry point absolutely. Everything else is in `designer_app/frozen.py`."""

from designer_app.frozen import main

raise SystemExit(main())
