"""observatory — the archive's statistics page.

Reads the episode extractions the pipeline already caches and renders one
self-contained HTML file. Nothing here runs during the weekly pipeline; it is a
separate, offline, read-only pass over the archive (see OBSERVATORY.md).

    build_observatory.py   entry point: argparse, I/O, reports
    stats.py               pure: (episodes, transcripts, show, obs) -> STATS dict
    defaults.py            resolve(show, obs, n_eps) -> a fully-populated Observatory
    place_coords.py        the bundled place -> [lat, lon] lookup
    assemble.py            inject STATS/theme/copy/vendor into template.html
"""
