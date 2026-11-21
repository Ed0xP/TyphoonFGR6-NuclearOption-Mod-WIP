OFF_COL = (0.19, 0.26, 0.215)
LIT_COL = (0.34, 0.80, 0.40)
KEYS = {
    "glare": {"RDR": "radar", "FLIR": "tcam", "IFF": "off", "PA": "off", "ELEV": "off", "HSI": "off", "DASS": "dass", "WPN": "wpn",
              "STOR": "stor", "FUEL": "fuel", "ENG": "eng", "AP|AT": "fa", "HDG": "off", "TRK": "off", "ALT": "off", "SPD": "off",
              "CLM": "off", "ATK": "atk", "APP": "app", "EMGY": "off"},
    "cu": {"FLIR": "ir", "BARO|RAD": "low", "DCLT": "off", "GS|M": "off", "LOCK|VV": "lock", "COM2": "off", "MIDS": "mids", "TCN": "off"},
    "ld": {"ATCK": "atk", "FUEL": "pfuel", "ENG": "peng", "HYD": "phyd", "GPS": None, "*": "off"},
    "cd": {"RWS": "radar", "AIR|OFF": "noradar", "MAP|TAC": "map", "TRK|NTH": None, "*": "off"},
    "rd": {"FUEL": "pfuel", "ENG": "peng", "HYD": "phyd", "WPT": "wpt", "STOR": "stor", "HUD": "hud", "FLIR": "ir", "LOCK": "lock",
           "DASS": "dass", "*": "off"},
    "ped": {"NVE": "night", "FLIR": "tcam", "GND": "gnd", "T/O": "to", "AA": "aa", "NAV": "nav"},
    "misc": {"REV": "off", "AGE": "off", "JETT": "off", "REC": "off", "EMGY": "off"},
}


def key_state(l):
    x, y, z = l["pos"]
    green = l["col"][1] > l["col"][0] + 0.2
    if l["src"] != "labels_panel.json":
        zn = "ped" if l["src"] == "labels_nve.json" else "misc"
        return KEYS[zn].get(l["text"]) if green else None
    if x > 0.15 and z > 0.90:
        zn = "misc"
    elif x < -0.10 and z > 0.90:
        zn = "glare"
    elif abs(x) < 0.08 and z > 0.97:
        zn = "cu"
    elif x < -0.11 and 0.64 < z < 0.88:
        zn = "ld"
    elif abs(x) < 0.105 and 0.63 < z < 0.82:
        zn = "cd"
    elif x > 0.11 and 0.69 < z < 0.88:
        zn = "rd"
    else:
        return None
    t = KEYS[zn]
    if l["text"] in t:
        return t[l["text"]]
    return t.get("*") if green else None
