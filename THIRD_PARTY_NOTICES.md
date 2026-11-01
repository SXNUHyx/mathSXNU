# Third-party components

## KaTeX 0.16.22

Source: https://github.com/KaTeX/KaTeX (npm package `katex@0.16.22`).

The files under `static/vendor/katex/` contain the KaTeX runtime, auto-render helper, CSS and fonts from the official npm distribution. The package was downloaded with npm's integrity verification. These local assets allow classroom formulas to render without contacting a CDN.

Copyright (c) 2013–2020 Khan Academy and other contributors. Licensed under the MIT License; the complete upstream notice is retained in [static/vendor/katex/LICENSE](static/vendor/katex/LICENSE).

Python dependencies, including Django, Pillow, olefile, qrcode, WhiteNoise and Gunicorn, are installed from the pinned versions in `requirements.txt` and carry their respective upstream licenses in the installed distributions.
