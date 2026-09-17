"""
Pure-Python JPEG EXIF GPS reader.
No Pillow, no piexif, no compiled extensions needed.
Works on any Python 3.6+ with only stdlib.
"""
import struct

def _read_rational(data, offset, big_endian):
    fmt = '>II' if big_endian else '<II'
    num, den = struct.unpack_from(fmt, data, offset)
    return num / den if den else 0.0

def _read_tag_value(data, ifd_offset, tag_type, count, value_offset_raw, big_endian):
    """Read a tag's value. value_offset_raw is the 4-byte field from the IFD entry."""
    endian = '>' if big_endian else '<'

    # Type sizes
    sizes = {1:1, 2:1, 3:2, 4:4, 5:8, 7:1, 9:4, 10:8}
    type_size = sizes.get(tag_type, 1)
    total = type_size * count

    if total <= 4:
        # Wert steht INLINE im 4-Byte Value-Feld selbst (nicht an externer Stelle!)
        source = struct.pack('>I', value_offset_raw) if big_endian else struct.pack('<I', value_offset_raw)
        offset = 0
    else:
        # Wert steht an externer Stelle, value_offset_raw ist ein Offset ab TIFF-Start
        source = data
        offset = value_offset_raw

    if tag_type == 2:  # ASCII
        end = source.find(b'\x00', offset)
        if end == -1:
            end = len(source)
        return source[offset:end].decode('ascii', errors='replace')

    if tag_type == 5:  # RATIONAL (unsigned) – nie inline (8 Byte/Wert), immer extern
        result = []
        for i in range(count):
            result.append(_read_rational(data, offset + i*8, big_endian))
        return result if count > 1 else result[0]

    if tag_type == 3:  # SHORT
        vals = [struct.unpack_from(f'{endian}H', source, offset + i*2)[0] for i in range(count)]
        return vals if count > 1 else vals[0]

    if tag_type == 4:  # LONG
        vals = [struct.unpack_from(f'{endian}I', source, offset + i*4)[0] for i in range(count)]
        return vals if count > 1 else vals[0]

    return None

def read_gps_from_jpeg(filepath):
    """Return (lat, lng) or (None, None) — pure Python, no deps."""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()

        # Find ALL EXIF APP1 segments (manche Kameras/Apps schreiben mehrere) –
        # versuche jedes der Reihe nach, bis eines mit GPS-Daten gefunden wird.
        i = 0
        exif_candidates = []
        while i < len(data) - 4:
            if data[i] == 0xFF:
                marker = data[i+1]
                if marker == 0xE1:  # APP1
                    length = struct.unpack('>H', data[i+2:i+4])[0]
                    segment = data[i+4:i+2+length]
                    if segment[:6] in (b'Exif\x00\x00', b'Exif\x00\xFF'):
                        exif_candidates.append(segment[6:])
                    i += 2 + length
                elif marker in (0xD8, 0xD9, 0xDA):
                    i += 2
                elif marker == 0x00:
                    i += 1
                else:
                    try:
                        length = struct.unpack('>H', data[i+2:i+4])[0]
                        i += 2 + length
                    except Exception:
                        i += 2
            else:
                i += 1

        if not exif_candidates:
            return None, None

        for exif_data in exif_candidates:
            result = _try_parse_exif_gps(exif_data)
            if result != (None, None):
                return result
        return None, None

    except Exception:
        pass
    return None, None


def _try_parse_exif_gps(exif_data):
    """Versucht GPS aus einem einzelnen EXIF-Datenblock zu lesen."""
    try:

        # Determine byte order
        bom = exif_data[:2]
        if bom == b'II':
            big_endian = False
        elif bom == b'MM':
            big_endian = True
        else:
            return None, None

        endian = '>' if big_endian else '<'

        # IFD0 offset
        ifd0_offset = struct.unpack_from(f'{endian}I', exif_data, 4)[0]

        # Read IFD0 to find GPS IFD pointer (tag 0x8825)
        gps_ifd_offset = None
        try:
            num_entries = struct.unpack_from(f'{endian}H', exif_data, ifd0_offset)[0]
            for n in range(num_entries):
                entry_offset = ifd0_offset + 2 + n * 12
                tag   = struct.unpack_from(f'{endian}H', exif_data, entry_offset)[0]
                ttype = struct.unpack_from(f'{endian}H', exif_data, entry_offset+2)[0]
                count = struct.unpack_from(f'{endian}I', exif_data, entry_offset+4)[0]
                voff  = struct.unpack_from(f'{endian}I', exif_data, entry_offset+8)[0]
                if tag == 0x8825:  # GPSInfo
                    gps_ifd_offset = voff
                    break
        except Exception:
            return None, None

        if gps_ifd_offset is None:
            return None, None

        # Read GPS IFD
        gps = {}
        try:
            num_gps = struct.unpack_from(f'{endian}H', exif_data, gps_ifd_offset)[0]
            for n in range(num_gps):
                entry_offset = gps_ifd_offset + 2 + n * 12
                tag   = struct.unpack_from(f'{endian}H', exif_data, entry_offset)[0]
                ttype = struct.unpack_from(f'{endian}H', exif_data, entry_offset+2)[0]
                count = struct.unpack_from(f'{endian}I', exif_data, entry_offset+4)[0]
                voff  = struct.unpack_from(f'{endian}I', exif_data, entry_offset+8)[0]
                val   = _read_tag_value(exif_data, gps_ifd_offset, ttype, count, voff, big_endian)
                gps[tag] = val
        except Exception:
            return None, None

        # GPS tags: 1=LatRef, 2=Lat, 3=LngRef, 4=Lng
        if 2 not in gps or 4 not in gps:
            return None, None

        def dms_to_dec(dms, ref):
            if isinstance(dms, list) and len(dms) == 3:
                dec = dms[0] + dms[1]/60 + dms[2]/3600
            elif isinstance(dms, (int, float)):
                dec = float(dms)
            else:
                return None
            ref = ref.strip().upper() if isinstance(ref, str) else 'N'
            if ref in ('S', 'W'):
                dec = -dec
            return round(dec, 6)

        lat_ref = gps.get(1, 'N')
        lng_ref = gps.get(3, 'E')
        lat = dms_to_dec(gps[2], lat_ref)
        lng = dms_to_dec(gps[4], lng_ref)

        if (lat is not None and lng is not None
                and -90 <= lat <= 90 and -180 <= lng <= 180
                and not (lat == 0 and lng == 0)):
            return lat, lng

    except Exception:
        pass
    return None, None
