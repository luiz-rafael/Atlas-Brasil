"use client";

import { useState } from "react";
import Link from "next/link";

export default function CorrecaoPage() {
  const [msg, setMsg] = useState("");
  const [email, setEmail] = useState("");
  const [entidade, setEntidade] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Enviando…");
    try {
      const api = process.env.NEXT_PUBLIC_ATLAS_API || "http://localhost:8000";
      const res = await fetch(`${api}/v1/correcoes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mensagem: msg,
          email: email || null,
          entidade_id: entidade || null,
        }),
      });
      if (!res.ok) {
        // fallback local
        const local = await fetch("/api/v1/correcoes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mensagem: msg,
            email: email || null,
            entidade_id: entidade || null,
          }),
        });
        if (!local.ok) throw new Error("falha");
        setStatus("Registrado (API local Next). Obrigado.");
      } else {
        setStatus("Registrado. Obrigado pela correção.");
      }
      setMsg("");
    } catch {
      setStatus("Não foi possível enviar agora. Tente de novo.");
    }
  }

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Encontrou um erro?</h1>
        <p className="muted">
          Fonte incorreta, relação sem evidência, homônimo, status jurídico
          desatualizado — reporte aqui.
        </p>
      </div>

      <form className="stack" onSubmit={submit}>
        <input
          className="filters"
          style={{ width: "100%", padding: "0.6rem" }}
          placeholder="ID da entidade (opcional, ex. p_lula)"
          value={entidade}
          onChange={(e) => setEntidade(e.target.value)}
        />
        <textarea
          required
          minLength={10}
          rows={5}
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Descreva o erro e a fonte correta…"
          style={{
            width: "100%",
            background: "var(--bg-elevated)",
            border: "1px solid var(--line)",
            color: "var(--ink)",
            padding: "0.75rem",
            borderRadius: 4,
            font: "inherit",
          }}
        />
        <input
          type="email"
          placeholder="E-mail (opcional)"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{
            width: "100%",
            background: "var(--bg-elevated)",
            border: "1px solid var(--line)",
            color: "var(--ink)",
            padding: "0.6rem",
            borderRadius: 4,
            font: "inherit",
          }}
        />
        <button className="btn" type="submit">
          Enviar correção
        </button>
      </form>
      {status ? <p className="prose-note">{status}</p> : null}
      <p className="faint">
        <Link href="/metodologia">Metodologia</Link>
      </p>
    </div>
  );
}
