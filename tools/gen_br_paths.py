"""Gera paths SVG simplificados dos estados do Brasil."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "brazil-states.geojson"
OUT = ROOT / "web" / "src" / "lib" / "br-states-paths.ts"

NAME_UF = {
    "Acre": "AC",
    "Alagoas": "AL",
    "Amapá": "AP",
    "Amazonas": "AM",
    "Bahia": "BA",
    "Ceará": "CE",
    "Distrito Federal": "DF",
    "Espírito Santo": "ES",
    "Goiás": "GO",
    "Maranhão": "MA",
    "Mato Grosso": "MT",
    "Mato Grosso do Sul": "MS",
    "Minas Gerais": "MG",
    "Pará": "PA",
    "Paraíba": "PB",
    "Paraná": "PR",
    "Pernambuco": "PE",
    "Piauí": "PI",
    "Rio de Janeiro": "RJ",
    "Rio Grande do Norte": "RN",
    "Rio Grande do Sul": "RS",
    "Rondônia": "RO",
    "Roraima": "RR",
    "Santa Catarina": "SC",
    "São Paulo": "SP",
    "Sergipe": "SE",
    "Tocantins": "TO",
}

minx, maxx, miny, maxy = -74.0, -34.0, -34.0, 6.0
W, H, pad = 1000.0, 920.0, 40.0


def proj(lon: float, lat: float):
    x = pad + (lon - minx) / (maxx - minx) * (W - 2 * pad)
    y = pad + (maxy - lat) / (maxy - miny) * (H - 2 * pad)
    return x, y


def simplify(coords, step=14):
    pts = coords[::step]
    if pts and pts[-1] != coords[-1]:
        pts.append(coords[-1])
    return pts


def ring_to_d(ring):
    pts = [proj(lon, lat) for lon, lat in simplify(ring)]
    if len(pts) < 3:
        return ""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for x, y in pts[1:]:
        d += f" L{x:.1f} {y:.1f}"
    return d + " Z"


def main():
    gj = json.loads(RAW.read_text(encoding="utf-8"))
    states = {}
    for f in gj["features"]:
        props = f["properties"]
        name = props.get("name") or props.get("NAME") or ""
        uf = NAME_UF.get(name)
        if not uf:
            continue
        geom = f["geometry"]
        paths = []
        if geom["type"] == "Polygon":
            paths.append(ring_to_d(geom["coordinates"][0]))
        else:
            for poly in geom["coordinates"]:
                paths.append(ring_to_d(poly[0]))
        ring = (
            geom["coordinates"][0][0]
            if geom["type"] == "MultiPolygon"
            else geom["coordinates"][0]
        )
        sx = sy = 0.0
        sample = ring[::5]
        for lon, lat in sample:
            x, y = proj(lon, lat)
            sx += x
            sy += y
        n = max(1, len(sample))
        states[uf] = {
            "uf": uf,
            "nome": name,
            "d": " ".join(p for p in paths if p),
            "x": round(sx / n, 1),
            "y": round(sy / n, 1),
        }

    lines = [
        "/** Paths SVG simplificados dos estados (viewBox 0 0 1000 920). Auto-gerado. */",
        "export type BrStatePath = { uf: string; nome: string; d: string; x: number; y: number };",
        "export const BR_STATE_PATHS: BrStatePath[] = [",
    ]
    for uf in sorted(states):
        s = states[uf]
        lines.append(
            "  { uf: %s, nome: %s, d: %s, x: %s, y: %s },"
            % (
                json.dumps(s["uf"]),
                json.dumps(s["nome"], ensure_ascii=False),
                json.dumps(s["d"]),
                s["x"],
                s["y"],
            )
        )
    lines.append("];")
    lines.append(
        "export const BR_STATE_BY_UF = Object.fromEntries(BR_STATE_PATHS.map((s) => [s.uf, s]));"
    )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("states", len(states), "bytes", OUT.stat().st_size)


if __name__ == "__main__":
    main()
