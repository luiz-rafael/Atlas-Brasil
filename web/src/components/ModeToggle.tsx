"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export default function ModeToggle() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const modo = sp.get("modo") === "pesquisador" ? "pesquisador" : "leigo";

  function setModo(m: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("modo", m);
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="mode-toggle" title="Modo de interface">
      <button
        type="button"
        className={modo === "leigo" ? "active" : ""}
        onClick={() => setModo("leigo")}
      >
        Leigo
      </button>
      <button
        type="button"
        className={modo === "pesquisador" ? "active" : ""}
        onClick={() => setModo("pesquisador")}
      >
        Pesquisador
      </button>
      {modo === "pesquisador" ? (
        <Link href="/api-docs" className="faint" style={{ marginLeft: 8, fontSize: 12 }}>
          API
        </Link>
      ) : null}
    </div>
  );
}
