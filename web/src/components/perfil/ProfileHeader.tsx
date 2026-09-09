import Link from "next/link";
import type { Entidade } from "@/lib/kb-types";
import type { ProfileTabId } from "./tabs";

function yearOf(d?: string | null) {
  if (!d) return null;
  const m = String(d).match(/^(\d{4})/);
  return m ? m[1] : null;
}

function currentMandate(pessoa: Entidade) {
  const list = [...(pessoa.mandatos || [])].filter(Boolean);
  if (!list.length) return null;
  const open = list.find((m) => !m.fim || String(m.fim) > "2026");
  return open || list.sort((a, b) => String(b.inicio || "").localeCompare(String(a.inicio || "")))[0];
}

function contactOf(pessoa: Entidade) {
  const email =
    (pessoa.email || "").trim() ||
    (pessoa.gabinete?.email || "").trim() ||
    null;
  const telefone = (pessoa.gabinete?.telefone || "").trim() || null;
  return { email, telefone };
}

function mailtoHref(email: string, nome: string) {
  const subject = encodeURIComponent(
    `Contato de cidadão — ${nome} (via Atlas Brasil)`
  );
  const body = encodeURIComponent(
    `Prezado(a) ${nome},\n\nEscrevo como cidadão(ã) a respeito de...\n\n(Descreva o tema com clareza e respeito.)\n\nAtenciosamente,\n`
  );
  return `mailto:${email}?subject=${subject}&body=${body}`;
}

function telHref(telefone: string) {
  const digits = telefone.replace(/\D/g, "");
  return digits ? `tel:+55${digits}` : `tel:${telefone}`;
}

export default function ProfileHeader({
  pessoa,
  onTab,
}: {
  pessoa: Entidade;
  onTab?: (tab: ProfileTabId) => void;
}) {
  const initials = pessoa.nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  const mandato = currentMandate(pessoa);
  const mandatoLabel = mandato
    ? `${yearOf(mandato.inicio) || "?"}–${yearOf(mandato.fim) || "…"}`
    : pessoa.no_poder_2026
      ? "Em exercício (corte atual)"
      : null;

  const { email, telefone } = contactOf(pessoa);
  const hasContact = Boolean(email || telefone || pessoa.pagina_oficial);

  return (
    <header className="atlas-profile-hero">
      <div className="atlas-profile-hero-main">
        {pessoa.foto_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="atlas-profile-photo"
            src={pessoa.foto_url}
            alt={`Foto oficial de ${pessoa.nome}`}
            width={104}
            height={104}
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="atlas-profile-photo atlas-profile-photo-fallback" aria-hidden>
            {initials}
          </div>
        )}
        <div className="atlas-profile-identity">
          <p className="eyebrow">Pessoa · registro público</p>
          <h1 className="atlas-profile-name">{pessoa.nome}</h1>
          {pessoa.nome_civil && pessoa.nome_civil !== pessoa.nome ? (
            <p className="faint">Nome civil / urna: {pessoa.nome_civil}</p>
          ) : null}
          <p className="atlas-profile-role">
            {[pessoa.cargo_atual || "Cargo não informado", pessoa.partido, pessoa.uf]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {mandatoLabel ? (
            <p className="atlas-profile-mandate">
              Mandato {mandato?.cargo ? `(${mandato.cargo})` : "atual"}{" "}
              <strong>{mandatoLabel}</strong>
              {mandato?.partido ? ` · ${mandato.partido}` : ""}
            </p>
          ) : (
            <p className="atlas-profile-mandate faint">
              Sem intervalo de mandato documentado neste corte
            </p>
          )}

          {(email || telefone) && (
            <dl className="atlas-profile-contact">
              {email ? (
                <div>
                  <dt>E-mail</dt>
                  <dd>
                    <a href={mailtoHref(email, pessoa.nome)}>{email}</a>
                  </dd>
                </div>
              ) : null}
              {telefone ? (
                <div>
                  <dt>Telefone</dt>
                  <dd>
                    <a href={telHref(telefone)}>{telefone}</a>
                    {pessoa.gabinete?.sala
                      ? ` · sala ${pessoa.gabinete.sala}`
                      : ""}
                  </dd>
                </div>
              ) : null}
            </dl>
          )}

          <p className="prose-note">
            O Atlas documenta cargos, partidos e relações com fonte — não produz
            veredito moral.
          </p>
        </div>
      </div>

      <div className="atlas-profile-actions">
        <Link
          className="btn"
          href={`/grafo?centro=${encodeURIComponent(pessoa.id)}`}
        >
          Explorar relações
        </Link>
        <Link
          className="btn-outline"
          href={`/timeline?pessoa=${encodeURIComponent(pessoa.id)}`}
        >
          Linha do tempo
        </Link>
        <button
          type="button"
          className="btn-outline"
          onClick={() => onTab?.("trajetoria")}
        >
          Trajetória
        </button>
        {pessoa.pagina_oficial ? (
          <a
            className="btn-ghost"
            href={pessoa.pagina_oficial}
            target="_blank"
            rel="noreferrer"
          >
            Página oficial
          </a>
        ) : null}
        {pessoa.uf &&
        (pessoa.cargo_atual || "").toLowerCase().includes("governador") ? (
          <Link className="btn-ghost" href={`/territorios/${pessoa.uf}`}>
            Ver território
          </Link>
        ) : null}
      </div>

      <aside className="atlas-profile-cobrar">
        <p className="atlas-profile-cobrar-title">
          Insatisfeito com algo? Cobre seu político.
        </p>
        <p className="muted">
          Use o canal oficial abaixo. O Atlas só facilita o contato — não
          intermediamos mensagem nem registra reclamação.
        </p>
        <div className="atlas-profile-actions">
          {email ? (
            <a className="btn" href={mailtoHref(email, pessoa.nome)}>
              Enviar e-mail
            </a>
          ) : null}
          {telefone ? (
            <a className="btn-outline" href={telHref(telefone)}>
              Ligar
            </a>
          ) : null}
          {pessoa.pagina_oficial ? (
            <a
              className="btn-outline"
              href={pessoa.pagina_oficial}
              target="_blank"
              rel="noreferrer"
            >
              Falar pela página oficial
            </a>
          ) : null}
          {!hasContact ? (
            <span className="faint">
              Sem e-mail ou telefone público neste corte. Consulte a Casa
              Legislativa ou o gabinete.
            </span>
          ) : null}
        </div>
      </aside>
    </header>
  );
}
