# Vendored assets

The observatory renders one self-contained HTML file: no CDN, no bundler, no
network at view time. That means these three assets are inlined into the output at
build time, so they are committed here rather than installed.

All three are **ISC**, which permits redistribution and requires that the copyright
notice and permission notice travel with the copies. That is what this file is for —
keep it next to the assets, and keep the notices intact if you re-minify or upgrade.
ISC is compatible with this repo's MIT license (see ../../LICENSE); the notices below
cover the vendored files, and the built HTML embeds them.

Verify what's here matches what was published:

```sh
cd observatory/vendor && shasum -a 256 -c SHA256SUMS
```

| File | Version | Bytes | License |
|---|---|---|---|
| `d3.v7.min.js` | 7.9.0 | 279,706 | ISC — © 2010–2023 Mike Bostock |
| `topojson-client.min.js` | 3.1.0 | 7,169 | ISC — © 2012–2019 Michael Bostock |
| `world-110m.json` | world-atlas 2.0.2 | 107,761 | ISC (packaging) over public-domain Natural Earth data |

Sources:

- d3 — <https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js> (<https://github.com/d3/d3>)
- topojson-client — <https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js> (<https://github.com/topojson/topojson-client>)
- world-110m.json — <https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json> (<https://github.com/topojson/world-atlas>), renamed on the way in. 1:110m scale, `objects: {countries, land}`.

### Notes

**Why the whole of d3.** The page uses maybe eight of its modules (geo, force, scale,
selection, drag, zoom, interpolate, timer, polygon). A custom rollup bundle would cut
280 KB to roughly 90 KB — and would put a Node toolchain in a Python repo to save
~190 KB on a page that gzips to around a quarter of its size and is opened once.
Not worth it. If page weight ever becomes a real complaint, the STATS payload is the
bigger half anyway and it scales with the archive; start there.

**Natural Earth.** The underlying map data is explicitly public domain
(<https://www.naturalearthdata.com/about/terms-of-use/>); the ISC notice covers
topojson's packaging of it.

**This is the only JavaScript in the repo.** No linter, formatter, or CI job here
knows about it, and none should — these files are opaque third-party artifacts. Don't
reformat them, and don't add a JS toolchain on their account. To upgrade: re-fetch
from the URLs above, update the version, byte count, and hash here, then run the
observatory test — it builds the fixture archive end to end and will catch an API
break.

---

## d3 7.9.0 — ISC

```
Copyright 2010-2023 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

## topojson-client 3.1.0 — ISC

```
Copyright 2012-2019 Michael Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

## world-atlas 2.0.2 — ISC

```
Copyright 2013-2019 Michael Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```
