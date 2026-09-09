/**
 * Controles temporais — Form GET puro (funciona sem JS do cliente).
 */

import Link from "next/link";

export default function TemporalControls({
  centro,
  profundidade,
  ano = 2026,
  modo = "resumo",
  expand,
}: {
  centro: string;
  profundidade: number;
  ano?: number;
  modo?: string;
  expand?: string | null;
}) {
  const years = [
    1985, 1990, 1995, 2000, 2005, 2010, 2014, 2016, 2018, 2020, 2022, 2024, 2026,
  ];

  const qs = (y: number) => {
    const p = new URLSearchParams();
    p.set("centro", centro);
    p.set("modo", modo);
    p.set("profundidade", String(profundidade));
    p.set("de", "1985");
    p.set("ate", String(y));
    p.set("ano", String(y));
    if (expand) p.set("expand", expand);
    return `/grafo?${p.toString()}`;
  };

  return (
    <div className="temporal-bar">
      <form method="get" action="/grafo" className="temporal-row">
        <input type="hidden" name="centro" value={centro} />
        <input type="hidden" name="modo" value={modo} />
        <input type="hidden" name="profundidade" value={String(profundidade)} />
        {expand ? <input type="hidden" name="expand" value={expand} /> : null}
        <input type="hidden" name="de" value="1985" />
        <label className="faint" htmlFor="ate-atlas">
          Até o ano
        </label>
        <input
          id="ate-atlas"
          type="number"
          name="ate"
          min={1985}
          max={2026}
          defaultValue={ano}
          style={{ width: 90 }}
        />
        <button className="btn" type="submit">
          Aplicar
        </button>
      </form>
      <div className="chips">
        {years
          .filter((y) => y >= 2005 || y === 1985)
          .map((y) => (
            <Link
              key={y}
              className="chip"
              href={qs(y)}
              style={
                ano === y
                  ? { borderColor: "var(--accent)", color: "var(--ink)" }
                  : undefined
              }
            >
              {y}
            </Link>
          ))}
      </div>
      <p className="faint">
        Relações com período após o ano selecionado saem do desenho.
      </p>
    </div>
  );
}
