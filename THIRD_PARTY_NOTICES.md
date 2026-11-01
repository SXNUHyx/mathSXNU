# Third-party components

## MathLive 0.111.4

Source: https://github.com/arnog/mathlive (official npm package `mathlive@0.111.4`).
The local browser bundle and fonts are in `static/vendor/mathlive/`. The editor
runs locally and is distinct from the commercial MathType service. The full MIT
notice is retained in [static/vendor/mathlive/LICENSE.txt](static/vendor/mathlive/LICENSE.txt).
The bundled KaTeX fonts carry the upstream KaTeX MIT notice described below.

## MathType Generic Integration 8.15.4

Source: https://github.com/wiris/html-integrations/tree/master/packages/generic
(official npm package `@wiris/mathtype-generic@8.15.4`, integrity verified by npm).
The unmodified integration bundle is in `static/vendor/mathtype/`; the upstream
MIT notice is retained in [static/vendor/mathtype/LICENSE](static/vendor/mathtype/LICENSE).
This license covers the integration code, **not** the MathType editor or its
hosted/backend services. Those require separate authorization from WIRIS.
The service is disabled by default. No public demo endpoint is configured.

## KaTeX 0.16.22

Source: https://github.com/KaTeX/KaTeX (npm package `katex@0.16.22`).

The files under `static/vendor/katex/` contain the KaTeX runtime, auto-render helper, CSS and fonts from the official npm distribution. The package was downloaded with npm's integrity verification. These local assets allow classroom formulas to render without contacting a CDN.

Copyright (c) 2013–2020 Khan Academy and other contributors. Licensed under the MIT License; the complete upstream notice is retained in [static/vendor/katex/LICENSE](static/vendor/katex/LICENSE).

Python dependencies, including Django, Pillow, olefile, qrcode, WhiteNoise and Gunicorn, are installed from the pinned versions in `requirements.txt` and carry their respective upstream licenses in the installed distributions.
