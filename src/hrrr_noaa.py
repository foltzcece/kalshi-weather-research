"""
HRRR 2 m temperature straight from NOAA's NOMADS server (free, no daily cap).
Downloads a tiny GRIB2 cutout around each airport for each forecast hour and decodes it here
(simple packing, no extra libraries). Used by live.py for the HRRR rest-of-day peak.
"""
import struct, time, datetime as dt, urllib.request

BASE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl"
BOX = 0.06   # degrees around the airport (~5 km), averaged


def _decode(b):
    """Values from a single-message GRIB2 with simple packing (template 5.0), no bitmap."""
    i = 16; npts = ref = e = d = nbits = None; data = None
    while i < len(b) - 4 and b[i:i + 4] != b"7777":
        L, n = struct.unpack(">IB", b[i:i + 5])
        if n == 5:
            npts = struct.unpack(">I", b[i + 5:i + 9])[0]
            assert struct.unpack(">H", b[i + 9:i + 11])[0] == 0, "not simple packing"
            ref = struct.unpack(">f", b[i + 11:i + 15])[0]
            raw_e, raw_d = struct.unpack(">HH", b[i + 15:i + 19])
            e = -(raw_e & 0x7FFF) if raw_e & 0x8000 else raw_e
            d = -(raw_d & 0x7FFF) if raw_d & 0x8000 else raw_d
            nbits = b[i + 19]
        elif n == 6:
            assert b[i + 5] == 255, "bitmap not supported"
        elif n == 7:
            data = b[i + 5:i + L]
        i += L
    if nbits == 0:
        return [ref / 10 ** d] * npts
    bits = int.from_bytes(data, "big"); total = len(data) * 8
    return [(ref + ((bits >> (total - (k + 1) * nbits)) & ((1 << nbits) - 1)) * 2 ** e) / 10 ** d for k in range(npts)]


def _fetch(cycle, fh, lat, lon):
    url = (f"{BASE}?dir=%2Fhrrr.{cycle:%Y%m%d}%2Fconus&file=hrrr.t{cycle:%H}z.wrfsfcf{fh:02d}.grib2"
           f"&var_TMP=on&lev_2_m_above_ground=on&subregion=&toplat={lat + BOX}&bottomlat={lat - BOX}"
           f"&leftlon={lon - BOX}&rightlon={lon + BOX}")
    req = urllib.request.Request(url, headers={"User-Agent": "kalshi-research-model"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
    if b[:4] != b"GRIB":
        raise ValueError("not available")
    v = _decode(b)
    return (sum(v) / len(v) - 273.15) * 9 / 5 + 32


def latest_cycle(now_utc, lat, lon):
    for back in (1, 2, 3, 4):
        c = (now_utc - dt.timedelta(hours=back)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
        try:
            _fetch(c, 1, lat, lon)
            return c
        except Exception:
            continue
    raise RuntimeError("no recent HRRR cycle on NOMADS")


def peak(lat, lon, now_utc, local_end_utc, cycle=None):
    """Warmest HRRR hourly 2 m temperature (F) between now and local midnight."""
    cycle = cycle or latest_cycle(now_utc, lat, lon)
    temps = []
    for fh in range(1, 19):
        valid = cycle + dt.timedelta(hours=fh)
        vu = valid.replace(tzinfo=dt.timezone.utc)
        if vu < now_utc:
            continue
        if vu >= local_end_utc:
            break
        temps.append(_fetch(cycle, fh, lat, lon))
        time.sleep(0.4)          # stay well under NOMADS' rate limit
    return max(temps) if temps else None


if __name__ == "__main__":
    now = dt.datetime.now(dt.timezone.utc)
    print("NYC HRRR peak rest of today:", peak(40.78, -73.97, now, now + dt.timedelta(hours=8)))
