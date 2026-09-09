"use client";

import { PROFILE_TABS, type ProfileTabId } from "./tabs";

export default function ProfileTabs({
  pessoaId,
  active,
  onChange,
}: {
  pessoaId: string;
  active: ProfileTabId;
  onChange: (tab: ProfileTabId) => void;
}) {
  return (
    <nav className="tabs profile-tabs" aria-label="Seções do perfil">
      {PROFILE_TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={active === t.id ? "active" : undefined}
          aria-current={active === t.id ? "page" : undefined}
          onClick={() => onChange(t.id)}
          data-pessoa={pessoaId}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
